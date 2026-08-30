# Environment assumptions registry (environment_assumptions)

**Protection level**: playbook

> This file registers host-environment assumptions that **hold in T2AG's code but are written down in no rule**.
> Assumptions of this kind never turn doctor red. They bite suddenly when you change host, sandbox or model, and
> then travel to the next person by word of mouth in a handoff.
>
> **This file is not**: an installation guide, a dependency list, or a troubleshooting manual. It answers exactly
> one question — "if this assumption stops holding, what will I see, and what should I do".

---

## 1. What this registry has to prove

The point of registering is to make environment assumptions **probeable**, not to make the environment correct.

So every `EA-XXXX` must be falsifiable by one read-only probe. Anything you cannot write a probe for is not an
environment assumption; it is a wish, and it does not enter this table.

**A probe reports facts and never auto-repairs.** If it detects that `.git` cannot unlink, it reports and must not
clean up on your behalf. If it detects `fitz` is missing, it reports and must not auto-install. The reason: auto-repair
turns "the environment is wrong" into "the environment was once wrong but you can no longer tell", and the person
taking over needs to be able to tell.

## 2. Fields

| Field | Meaning |
|---|---|
| **Assertion** | one falsifiable statement |
| **Code anchor that depends on it** | which code assumes it holds (by content anchor, never line number) |
| **Probe method** | a directly executable read-only command or check |
| **Correct reaction when the probe fails** | what the taker should do, and what they must **not** do |
| **First recorded** | date + which actual cost forced it out |

## 3. Relationship to doctor

The doctor atom `runtime.environment` implements the entries marked "probed" in this table. Level convention:

- **INFO**: the assumption does not hold but only some capability is affected; teaching may continue.
- **WARN**: the assumption does not hold and write operations will produce side effects that are hard to notice.

It is normal for this table to hold more entries than doctor implements — register first, implement later. The
reverse is not allowed: doctor must not probe an assumption that is not registered here.

---

## 4. Registered entries

### EA-0001 | `activity_close`'s production root derives from the repo root the code lives in

- **Assertion** (rewritten 2026-08-09, EV-0022): `activity_close.INSTANCE_ROOT` derives from the repo root of the
  code file (`Path(__file__).resolve().parents[2]`), and `PRODUCTION_ROOT` is only a compatibility alias.
  **The repo root of any installed instance is its own production root**: the direct_user authorization gate is in
  force on every instance. An explicit `--root` pointing elsewhere still requires `T2AG_022_CLOSE_TEST=1`
  (test/shadow guard unchanged). Before the rewrite this constant was a hard-coded literal of the maintainer's
  machine — on any other machine the authorization gate never fired, so external users effectively could not close
  an activity at all.
- **Code anchor that depends on it**: `grep -n "INSTANCE_ROOT\|PRODUCTION_ROOT" main/70_tools/activity_close.py`
  (the `root.resolve() == INSTANCE_ROOT` branch and the `T2AG_022_CLOSE_TEST` branch)
- **Probe method**: compare `activity_close.INSTANCE_ROOT` with the current `ROOT.resolve()`.
- **Correct reaction when the probe fails**: their derivation makes them identically equal; inequality means the
  code tree and the running root are misaligned (for example, running from a copy that was moved). Work out which
  copy of the code is running before doing anything.
  **Never set `T2AG_022_CLOSE_TEST=1` just to make apply pass** — that variable exists for testing, and using it to
  bypass the production gate is equivalent to deleting the gate. Also never change `INSTANCE_ROOT` back to any
  machine literal.
- **First recorded**: 2026-08-07. Before this, every handoff had to repeat a prose warning "never set that
  variable", because no mechanical means existed to say it.
- **doctor status**: probed (`runtime.environment`, reports INFO when unequal)

### EA-0002 | PyMuPDF (`fitz`) exists only inside `.venv`

- **Assertion**: `fitz` is not a global dependency of the host Python. Sandboxes and bare `python3` environments do not have it.
- **Code anchor that depends on it**: `grep -n "import fitz" main/70_tools/t2ag_source_pages.py` (the PPI back-calculation path, lazily imported)
- **Probe method**: `import fitz`.
- **Correct reaction when the probe fails**: know that the PPI back-calculation path of `source_pages prepare` is
  unavailable in this environment, and run it on a host that has `.venv`. **Never auto-`pip install`** — installing
  it in the sandbox does not mean it is installed on the host, and the next person will assume it was always there.
- **First recorded**: 2026-08-07. `source_pages prepare` failed outright in the sandbox and the failure message did
  not point at an environment assumption.
- **doctor status**: probed (`runtime.environment`; reports INFO when unavailable and names the affected command)
- **Scope limitation (added 2026-08-07)**: this entry covers **only the `fitz` path** (PPI back-calculation in
  `source_pages prepare`). It **does not mean "the sandbox cannot do PDF analysis"**. Measured as available in the
  sandbox: `pdfimages` / `pdffonts` / `pdftotext` / `pdftoppm` / `qpdf` (poppler-utils), `pypdf`, `pdfplumber`,
  `PIL`, `numpy`, `pdflatex` / `xelatex`. All the read-only PDF measurements in
  `T2AG_LAYOUT_CRITICAL_CRITERION_REPORT_2026-08-07.md` (fonts, text layer, image objects, page dimensions) were
  done inside the sandbox without `fitz`.
  **Misreading this entry as "anything PDF-related goes to the host" causes unnecessary blocking** — that misreading
  has already happened once, in stage A1 of that report.

- **The three-way split (added 2026-08-23, against the mirror misreading)**: the entry above guards against
  "send everything to the host"; this one guards against its mirror — "`pdftoppm` can stand in for `fitz`".
  **It can stand in for rendering, not for geometry**:

  | Purpose | Means available here | Without `fitz` |
  |---|---|---|
  | **Rendering** (re-rendering page images) | `fitz` or `pdftoppm` | **Can proceed** — see the page-image cache under `book/.cache/` |
  | **PPI back-calculation** (the geometry gate of `source_pages prepare`; reads the MediaBox) | **currently `fitz` only** | **Fail-closed; must go to the host** |
  | **Other read-only analysis** (fonts / text layer / image objects / page dimensions) | `pypdf` / `pdfplumber` / `pdftotext` / `pdfimages` / `pdffonts` / `qpdf` | Can proceed |

  Until a `pypdf` / `pdfinfo` MediaBox fallback is actually implemented, neither doctor nor any document may
  describe `pdftoppm` as a fallback that lets `prepare` continue — that would leave people believing the gate
  passed when in fact it never ran. Whether to implement that fallback is a scheduling question, not an
  adjudication; while it is unimplemented, stating the three rows honestly is enough.

### EA-0003 | Some mounts can create files but cannot unlink (**scope is the whole mount, not just `.git`**)

> **Scope correction (2026-08-07 22:1x, measured)**: this entry originally read "can create files under `.git` but
> cannot unlink", which gets read as "the restriction is only in `.git`". Measured: **the entire mount cannot
> unlink**. `T2AC/`, `T2AC/t2ag/main/`, `T2AC/t2ag/main/40_course/**` and `outputs/` each returned
> `Operation not permitted` on `rm` after `touch`; only `/tmp` allows deletion.
>
> **Two hard constraints follow (previously unwritten)**:
>
> 1. **The action "move a file" does not exist inside the sandbox.** `mv` = copy + unlink, and the second half must
>    fail. Any "migrate X to Y" task can only be done as a **copy** in this environment; deleting the old location
>    must be done by the user on the host. If a work order says "migrate", the executor must restate it as
>    "copy + pending host deletion" and must not claim the migration is done.
> 2. **Any probe that creates a temporary file must use a fixed name with a capped residue** (see "the probe's own
>    residue" at the end of this entry). On 2026-08-07 a bare `touch`/`rm` capability probe left 4 `.rmtest*` files
>    inside the mount; the executor could not clean them and had to leave them to the user. **The precedent already
>    existed in this very entry and was not followed.**

- **Assertion**: some mounts (this round: the Cowork sandbox's mount of a Windows directory) allow creating files
  but do not allow deleting **any** file. Git's lock-file protocol depends on "what I created I can delete", so
  `git commit` **appears to succeed** while leaving `HEAD.lock`, `objects/maintenance.lock` and `tmp_obj_*` behind.
  The same restriction makes moving, cleaning up, and in-place replacement (delete-then-write) of ordinary files
  unavailable in this environment.
- **Code anchor that depends on it**: not a piece of T2AG code — git's own lock protocol. Related rules:
  `grep -n "commit" main/50_playbook/git_workflow.md`.
- **Probe method**: create a temporary file under `.git/` and delete it. **The conclusion of this probe applies to
  the whole mount**; there is no need — and it is wrong — to repeat bare probes in other directories (repeating
  only manufactures undeletable residue).
- **Correct reaction when the probe fails**: **run no git write operation in this environment** (commit / add / tag
  / gc); do it on the host instead. Lock files already left behind are deleted manually by the user on the host —
  the probing party **must not** clean up on their behalf, because deleting `HEAD.lock` is a dangerous operation in
  a normal environment and must not become a routine action.
- **First recorded**: 2026-08-07. One sandbox `git commit` left three kinds of lock file; `HEAD.lock` makes the
  host's next ref update fail outright. The cost was the user manually deleting three files.
- **doctor status**: probed (`runtime.environment`, reports WARN when deletion is impossible)
- **The probe's own residue**: the probe file name is fixed at `.git/.t2ag_env_probe` (**no PID**). In an environment
  where this assumption does not hold the file cannot be deleted, and naming it per run would leave one more file
  every time doctor runs — the probe itself would become the disease. A fixed name caps the residue at one, and the
  next probe tries to delete it first. That file is safe to delete.

### EA-0004 | The WorkBuddy host does not support the parallel multi-agent assumption of the startup formation

- **Assertion**: `startup_orchestration.md` §1 assumes the host can run a **parallel** formation of "one Main
  Conductor + two helper agents". The WorkBuddy host cannot actually do true parallel multi-agent work — the three
  roles (Main / Runtime Sentinel / Context Prefetcher) degrade to **sequential execution by a single agent**. This
  assumption is written into no rule as a host precondition; it is only implicit in the playbook's formation prose.
- **Code anchor that depends on it**: not T2AG code — the playbook's formation narrative:
  `grep -n "two helper\|parallel\|single-agent degradation" main/50_playbook/startup_orchestration.md` (the formation description and
  degradation clause of §1 "goals and default topology").
- **Probe method**: on the host, try to spawn a read-only subtask **concurrently** using the agent capability and
  observe whether true parallelism holds and returns; or simply observe one startup — if all three roles complete
  one after another inside the same agent loop, the formation did not land.
- **Correct reaction when the probe fails**: take the **single-agent degradation** that playbook §1 explicitly
  allows ("single-agent degradation is permitted when helper-agent capability is unavailable; degradation changes
  no safety or authorization boundary"). Write "single-agent sequential execution" **truthfully** in the startup
  report; never describe sequential execution as "the parallel formation has completed"; and do not force-spawn
  concurrent sub-agents to manufacture the appearance of parallelism.
- **First recorded**: 2026-08-07. The student pointed out in a startup retrospective that "WorkBuddy actually
  cannot do multi-agent operation". This session's startup did in fact run all three roles sequentially in a single
  agent, but the opening report described it as a formation executing in parallel, concealing the absence of
  parallelism — and leaving the visual scan gate's cost with no concurrency to hide behind, landing in full on the
  critical path (see P-0057 factor 4, and P-0056).
- **doctor status**: not probed (newly registered). Multi-agent capability is a host capability rather than a
  filesystem/environment fact, so `runtime.environment` does not cover it yet; probe method above, implementation pending.

### EA-0005 | A host "connected folder" is not a "mounted folder" (mounting is lazy)

- **Assertion**: a folder declared "connected" in the Cowork host's session configuration **has not necessarily been
  mounted**. The declared surface (the paths listed in the session configuration and their `/sessions/<id>/mnt/<name>`
  mapping) and the actual surface (directories that really exist under `/sessions/*/mnt/`) may disagree; some folders
  materialize only after being **explicitly requested**. Startup checks run before materialization and see the actual surface.
- **Code anchor that depends on it**: `grep -n "def resolve_external_peer_root" main/70_tools/t2ag_doctor.py`
  (resolving the peer repo root by falling back on the mount basename; unresolvable means FAIL). Any code locating
  **out-of-repo** resources by mount point depends on this assumption.
- **Probe method**: compare the folder list declared in session configuration against the actual result of
  `ls -d /sessions/*/mnt/*/`. Anything in the former but not the latter is declared-connected but unmounted.
- **Correct reaction when the probe fails**: **request the mount first, then judge peer state.** Only if it is still
  unreachable after mounting can you talk about the peer having moved or disappeared. **Never** conclude from
  "the root did not resolve" that the peer repo is gone, and never delete a reference identity on that basis
  (`cross_repo_reference.md` §4: on a broken link, fix resolution first and do not touch reference identity).
  Also do not rewrite the hint path into whatever the current environment happens to resolve — `peer_root_hints`
  is an environment hint, not a reference identity.
- **First recorded**: 2026-08-08. At this session's startup `Trading-OS` was already in the declared list with
  its mapping written out, but did not exist under `/sessions/*/mnt/`, so `runtime.external_references` reported
  2 FAIL. The FAILs vanished the moment the mount was explicitly requested, and the recomputed sha256 of the peer's
  discipline file matched its sidecar binding bit for bit — **the binding was healthy throughout; what was red was
  the environment**. Cost: one root-cause investigation in the wrong direction, plus seriously considering
  "if the peer is unreachable, delete the reference" (which, if executed, would have deleted an intact discipline
  authority binding).
- **doctor status**: not probed (newly registered). The declared surface lives in the host session configuration,
  not in the repo, so T2AG cannot read it and cannot self-certify. Changed instead so that the unresolvable branch
  of `check_external_references` **prints the current mount surface** and points here, letting the reader tell the
  difference at a glance. **The level remains FAIL**: a peer repo disappearing entirely lands in the same branch,
  and downgrading would turn "the peer is completely gone" into an ignorable WARN.

---

## 4A. Cross-host deliverable specification (HOST_BYTE_DRIFT L4, adjudicated 2026-08-19)

Costs already paid: the 0.2.2 clone's newline rewrite made the frozen manifest SHA mismatch; on 08-06 a host tool
converted 83 files LF→CRLF; on 08-06 a `.ps1` without a BOM was decoded as GBK by PowerShell 5.1 (all four violated,
blowing up in argument parsing). Same root cause class: **artifact bytes depend on the host rather than the content**
(full case in `docs/handoffs/T2AG_HOST_BYTE_DRIFT_PREVENTION_PLAN_2026-08-06.md`; the L3 diagnostic layer is
adjudicated and pending construction).

Any delivery script that **executes across hosts**:

1. **Pure ASCII**, containing no non-ASCII bytes (avoids host codepage decoding — more thorough than "remember the BOM");
2. **LF newlines**;
3. Hash-type arguments are **computed at runtime**, never hard-coded file SHAs (a hard-coded payload SHA is fine; that is a content fingerprint);
4. **Assert non-empty** after reading a value, before passing it to a downstream command.

Verify before delivery: run one non-ASCII byte scan plus a quote-pairing self-check.
enforcement: prose_accepted (reason: delivery scripts are produced in out-of-repo sessions where doctor cannot see their birth point; failure visibility = the script blowing up on the host)

## 5. Adding entries

The bar for a new `EA-XXXX` is that **a real cost has already been paid**, not "this might go wrong". Speculative
entries dilute the table and stop people reading it line by line. Write the cost paid into "first recorded" — it is
the reason this entry exists.

## 6. Related files

- `main/50_playbook/handoff_management.md` §5.6 (assertion recomputation source; both descend from EV-0016)
- `main/50_playbook/git_workflow.md` (the normal-path rules for EA-0003)
- `main/70_tools/t2ag_doctor.py` (`check_environment_assumptions`)
- `main/70_tools/validation_workflow.json` (`runtime.environment` atom registration)
- `main/60_journal/t2ag_evolution_register.md` (EV-0016)
