# Git versioning and disaster recovery (git_workflow)

**Protection level**: core-playbook

> Git gives T2AG local version history, recovery from bad edits, change auditing and optional
> off-site backup.
> `core-playbook` means this process must be retained across releases; it does not mean every
> session close must commit or reach the network.

## 1. Triggers and run modes

Triggered by: enabling Git for the first time, archiving at session close, a course/system
milestone, a version release, or needing to recover a historical file.

| Mode | Determination | Behaviour at session close |
|---|---|---|
| `disabled` | the current directory is not inside a Git repository | skip and report truthfully |
| `local` | Git exists, with no remote or no network this time | may commit locally once authorized |
| `remote` | Git and a remote both exist | per-instance authorization by default; an approved bounded campaign Git plan may cover the local checkpoints it lists; the user performs the remote upload by hand |

Git is a protection layer, not the teaching source of truth. A course can still close when Git
is unavailable, and doctor plus the file write-back must still complete.

## 2. Safety boundaries

1. Look at status and diff before staging; never treat `git add .` as a daily default.
2. Stage only the T2AG files listed in this round's write confirmation, using explicit paths;
   any other change in the working tree belongs to the user or a parallel task.
3. Never commit `.env`, keys, tokens, virtual environments, caches or unconfirmed personal
   material. A remote holding a student profile defaults to Private.
4. In the default mode, the agent must obtain explicit authorization for the current operation
   before each `git add` or `git commit`.
   A `version_campaign` may cover the local checkpoints it lists only after the user has
   approved a limited Git plan enumerating the repositories, explicit paths, commit
   count/purpose, subject, stop conditions and expiry. An open-ended, cross-version or
   unlisted-path "continuous authorization" is void.
5. Never use `git reset --hard`, `git clean -fd` or `git push --force` on your own initiative.
   Stop and explain first on a conflict or a history rewrite.
6. The agent never runs `git push` or any other upload to a remote repository; it only produces
   manual upload instructions the user can verify.
7. Record commit success separately from the upload result the user reports; no network and no
   snapshot must never block the teaching file write-back.
8. `clean != reviewed != released`: a clean working tree says only that there is no uncommitted
   difference; an ordinary commit or a recovery checkpoint provides a restore point and never
   confers independent re-review or release qualification.
9. **Out-of-repo `docs/` tracking boundary** (DOCS-TRACKING-BOUNDARY, adjudicated 2026-08-19):
   the adjudication surface is **tracked by default** — work orders, adjudication records,
   candidates, seeds, design, reports, tools and the top-level index files
   (`docs/README.md`, `T2AG_PROGRESS.md`, `T2AG_PENDING_LEDGER_*.md`,
   `AUG_SHELL_WATCH.md`, `SEEDS.md`). Adjudication records are canonical and should not live
   outside the repo. Exemptions (listed explicitly in `.gitignore`):
   `docs/recovery_points/`, `docs/handoffs/backups/`, and generated artifacts under
   `docs/publishing/`. Background: the explicit-path discipline (items 1 and 2 of this section)
   made the tracked set decay naturally into "the union of whatever was named in an add", so
   partial tracking was a by-product of discipline rather than an adjudication — this clause
   supplies the boundary that ought to hold.
   Catching up still uses explicit directory paths and is not exempt from item 4's authorization.

### 2.1 The campaign Git plan

A bounded campaign Git plan must bind the `campaign_id`, the target version, the frozen
baseline, the repositories, explicit pathspecs, the permitted number and purpose of local
checkpoints, the commit subject, retained RT3 items, and the authorization expiry conditions.
Before each checkpoint you must still:

1. re-read the actual HEAD, working tree and index state;
2. show the explicit paths owned this round and the working-tree diff;
3. stage only the listed paths; never use `git add .`;
4. show `git diff --cached --check`, the cached diff, the index tree and the parent;
5. stop on an unlisted path, an unknown repository, a baseline change, a risk escalation, or an
   unknown FAIL/WARN, and do not consume the remaining allowance.

The plan covers no push, tag, reset, checkout, stash, history rewrite, deletion of recovery, or
any unlisted release capability. A release snapshot and a push are always separate capability
gates.

## 3. Enabling Git for the first time

```bash
git --version
git rev-parse --is-inside-work-tree
git init -b main                         # only after confirming this directory is the target repo
git config user.name "your commit name"  # prefer repo-level config; do not force a global identity
git config user.email "your commit email"
```

Before the first staging, check or create `.gitignore`, covering at least:

```gitignore
.venv/
__pycache__/
*.pyc
.env
```

The first commit also runs the section 4 preview flow first. Only a brand-new, dedicated,
manually confirmed repository may use a broader staging command after that preview.

## 4. Session close or milestone archiving

```bash
git status --short
git diff --check
git diff -- path/to/file1 path/to/file2
git add -- path/to/file1 path/to/file2
git diff --cached --check
git diff --cached
git commit -m "MATH1607H lesson01: update progress and knowledge-point retests"
```

- The paths come from the write confirmation in `session_close.md`, never guessed from the working tree.
- If something unrelated slipped into the staging area, stop the commit and unstage that path
  with `git restore --staged -- <path>`; do not change the working tree.
- A commit message states "course/system object + what actually changed"; never use empty words
  like `update` or `misc`.
- Do not manufacture an empty commit when there is no real difference.

Checkpoints come in three kinds, and the names must never be interchanged:

| Kind | Purpose | May it be called a release |
|---|---|---|
| evidence checkpoint | stores the file list, fingerprints, tests, WARNs and the recovery source; Git not required | no |
| recovery checkpoint | an authorized local intermediate commit, for recovering a defective tree or a construction boundary | no |
| release snapshot | binds the final HEAD/tree that passed the full candidate re-review and the finalization delta independent re-review | yes; limited to the local snapshot the report names, and never implies push/tag |

### 4.1 The bounded finalization protocol

Finalization permits only the exact state/report-pointer delta after the candidate passed its
full re-review, and follows this fixed order:

1. the release operator forms the exact working tree, stages by allowlist, and freezes the
   parent, the staged diff SHA and the index tree;
2. a reviewer on a different model or in a different session from the operator reviews
   semantics, paths and the global gates before the commit, recording the `expected tree`;
   the operator must never self-review;
3. only after the reviewer states `proposed_delta_passed` may the operator commit **that same**
   index tree;
4. after the commit, the reviewer verifies the parent, the commit tree, the actual diff SHA,
   the working tree and every indivisible global gate;
5. a tree mismatch, an extra path, an addition after the commit, a report written back, or an
   early PASS all fail this round of finalization.

The reviewer output is produced last, frozen immediately, and immutable. A final PASS is written
only into the external reviewer report; it must never be written back into the target repo, the
construction report or an index, which would create a fresh unreviewed delta. After the report
is written, any byte changing in the target repo voids the corresponding release snapshot
conclusion.

When a remote is configured and this round needs to sync, the agent only displays the commands
for the user to run by hand:

```bash
git remote -v
git push
```

When the remote is ahead of local, look at the difference first. Whether to `pull`, resolve
conflicts or upload is done by the user in their repository client.

## 5. Remotes and privacy

```bash
git remote add origin <remote repository URL>
git remote -v
git push -u origin main
```

- When it holds a student profile, course reflections or a trading log, the remote defaults to Private.
- A token goes only into the system authentication dialog or a credential manager; never write
  it into Markdown, a command-history example, or an `.env` that is then committed.
- The push rhythm is the student's decision; the agent only ever reminds and shows the list, and
  never performs the remote upload for the user.

## 6. Recovery and auditing

```bash
git log --oneline -- path/to/file
git diff <old commit> -- path/to/file
git show <commit>:path/to/file
```

When recovery is needed, show the target version first, then run this after the student confirms:

```bash
git restore --source <commit> -- path/to/file
git diff -- path/to/file
git add -- path/to/file
git commit -m "restore <file> to the confirmed version at <commit>"
```

`git restore -- <path>` discards uncommitted changes and may be used only after the student
explicitly asks to discard them. Prefer making the recovery a new commit, keeping the full audit
chain.

## 7. Interface with T2AG

| Situation | Git behaviour |
|---|---|
| the closing ritual | check status and diff; per-instance authorization by default, or create the listed local checkpoints per an approved campaign Git plan; the user uploads to the remote by hand |
| milestone completed | a commit is advised; create a tag only when a version or course rule explicitly requires one |
| doctor | checks `.venv`/`.env` tracking, version consistency, and the cross-release core/meta playbooks |
| version release | commit only after the changelog, the version number and the releases are all in sync |
| disaster recovery | read the history and show the target first, then restore a single file or an explicit scope |

## 8. Common errors

| Symptom | Handling |
|---|---|
| `Please tell me who you are` | set `user.name` and `user.email` for this repository |
| `rejected ... fetch first` | look at the remote difference; when it fast-forwards, `git pull --ff-only` |
| CRLF/LF warning | **not harmless**; handle per §11: check whether `git diff -w` is empty, and if it is, restore rather than commit |
| `hash binding mismatch` with a `LINE ENDING DRIFT` note | the host rewrote line endings; restore the file, and **do not** regenerate the plan or re-run the evidence matrix |
| push authentication failure | use system authentication or a token; never write credentials into a file |
| non-ASCII paths shown escaped | you may set `git config core.quotepath false` |
| unexplained changes already in the working tree | do not stage and do not restore; handle only the files explicitly owned this round |

## 9. Read-only replay of a release candidate

A candidate tree is not a daily teaching step. Candidate tree evidence may be generated only
when the user has explicitly entered release review, Main and Skeleton are in a quiet window,
and consecutive samples of the working tree show no change.

<!-- rule: CAND-REPLAY-003 -->
### 9.1 The 0.2.0 frozen acceptance boundary

The user froze this boundary on 2026-07-27. What is frozen is the 0.2.0 acceptance scope, not a
Git snapshot, and daily study is not paused. The 0.2.0 candidate tooling supports only the
current Windows/NTFS, an ordinary non-sparse Git repository, and an explicit teaching quiet
window. The final independent re-review may treat only the following six items, plus the
existing three-release gates, as blocking for this generation:

1. the candidate tool refuses an effective sparse state expressed by `core.sparseCheckout`,
   `core.sparseCheckoutCone`, `index.sparse` or `.git/info/sparse-checkout`, and has a negative
   case for "the working tree changed and the candidate silently missed it";
2. both Main and Skeleton can run `--preflight` under the current safe local configuration; an
   explicit `core.fsmonitor=false` is a safely-disabled state, and only an enabled value or an
   external monitor path is refused;
3. the candidate's final source fingerprint must occur after all A/B replays and cross-checks;
   that final fingerprint passing and returning successfully ends this quiet window, and new
   learning write-backs afterwards do not retroactively invalidate the point-in-time candidate
   already formed;
4. one doctor run reads and uses exactly one `ProgressSnapshot` per course;
5. every test helper declared as an "exact replacement" refuses both zero hits and repeated hits;
6. when Lite omits the original textbook document, the report status, the formal manifest path
   and SHA, the schema, the target kind, the operation count/sequence, and every
   source/target/disposition/outcome/post-target field must be verified.

<!-- rule: CAND-REPLAY-004 -->
The following enter the later hardening backlog and no longer block 0.2.0: extra metadata proof
for mode/File ID, Lite directory placeholders, the nanosecond concurrency window that cannot be
eliminated after the final check, cross-platform threats such as non-Windows/NTFS or SHA-256
Git, unusual mounts, and **a theoretical attack surface newly raised outside the manifest**.
Existing defensive implementations may stay; a reviewer must not move this generation's finish
line by demanding stronger proof. A fact outside the manifest may re-enter the 0.2.0 blocking
set only once it is shown to violate one of the six items above or an existing three-release gate.

"Read-only" against a real repository must cover the working tree, the index, refs and object
store metadata together. Merely setting a temporary index while configuring the real
`.git/objects` as an alternate can still freshen the mtime of real objects, which is not strict
isolation; that algorithm is forbidden, as are hardlinks, `git clone --shared`, `--reference`,
and any other copy method that shares an object store.

A conforming replay must:

1. establish prior fingerprints of the source repository's working-tree content, `HEAD`, refs,
   real index and `.git/objects` metadata;
2. physically copy the whole repository (working tree and `.git`) to a new temporary directory;
   the copy must not use hardlinks or alternates, and the candidate directory must not reference
   the source repository back;
3. inside the physical copy, mask user-level and system-level Git configuration, and run
   `read-tree HEAD -> add -A -- . -> write-tree -> diff --cached --check` with a fresh temporary
   index inside the copy;
4. before deleting the copy, replay independently in a second brand-new physical copy; the file
   count, tree SHA and whitespace results must agree;
5. re-take the source repository's full fingerprint only after all A/B cross-checks are done;
   any change in working-tree content, `HEAD`, refs, index, object count or object metadata
   immediately discards every candidate value from this round and reports the fact — a close
   value must never be written up as release evidence;
6. temporary-copy cleanup applies only to the exact directories resolved and confirmed to sit
   under the temporary root. A candidate operation never enters the real repository's `.git`,
   and "no new objects were created" never substitutes for proof that metadata is unchanged.

The conditions above are enforced by `main/70_tools/t2ag_candidate_replay.py` and may not be
replaced by hand-written copy commands or by a statement in a report. When the independent
re-review has passed but candidate authorization has not been given, only the source-repository
pre-check may run — it calls no Git and creates no copy:

```powershell
python -B main/70_tools/t2ag_candidate_replay.py --preflight
```

The tool must FAIL before any Git invocation when:

- the inherited environment contains `GIT_*` in any case form: clear them all first and inject
  only the config, attributes, exclude, hooks and index from the tool's control directory; never
  set an object directory or an alternate;
- `.git` is a gitfile/link, or there is a `commondir`, `gitdir`, `worktrees`, alternates,
  `config.worktree`, an external `core.worktree`, include/includeIf, a promisor/partial clone, a
  worktree filter, an enabled fsmonitor, an effective sparse checkout / sparse index, or a Git lock;
<!-- rule: CAND-REPLAY-001 -->
- the source root, the temporary root, either copy, or any of their ancestors or descendants
  contains a symlink, junction, or mount/reparse point;
- any regular file has a link count other than 1, a File ID repeats within one tree, or a File ID
  is reused between the source, A and B trees;
<!-- rule: CAND-REPLAY-002 -->
- a path collides under case or Unicode normalization, or the **per-file relative path, size and
  SHA-256** byte list of the source and of A/B are not exactly equal;
- during the copy or the replay, any file content, mode or mtime in the source repository
  changes, including HEAD, refs, index and object store metadata.

Only after the user has explicitly authorized this round's candidate may the generation entry
point run in a brand-new empty directory outside the source repository. The literal token is
only a misfire guard and never substitutes for user authorization:

```powershell
python -B main/70_tools/t2ag_candidate_replay.py `
  --generate `
  --workspace <a brand-new empty directory outside the source repo> `
  --authorization-token CANDIDATE_REPLAY_AUTHORIZED
```

The tool copies A and B byte for byte from the same verified source, and runs Git with a
pre-resolved and hashed executable, explicit `--git-dir`/`--work-tree`, and an index in a control
directory outside the copies. A candidate is emitted only when A and B agree on tree SHA, file
count and whitespace result, the copy working-tree bytes are unchanged, and the source
repository's full state before and after is identical.

While real learning is still writing back, Lite is not synced, the independent re-review has not
passed, or the user has not authorized a release review, the candidate state may only be recorded
as `revoked / not generated`; never chase a continuously changing tree SHA to refresh a report.

## 10. Teaching and release statements

- Uncommitted, no Git, and no network never block starting a lesson, the teaching write-back, or session close.
- After a change to a core-playbook, doctor, the directory structure or the cloud protocol,
  maintenance must end by producing a "pending snapshot list" and raising a `WARN`.
- Only with a recoverable local snapshot may a formal release, or a handoff-mandated generation
  acceptance, claim to be releasable.
- With no snapshot, report truthfully that "teaching can continue; the release snapshot is not
  complete", and never let a working-tree state pose as a released version.

## 11. Byte stability (canonical owner)

This section is the single current owner of **host-dependent byte drift**.

### 11.1 Why this is not fastidiousness about formatting

T2AG binds evidence to the SHA-256 of **file bytes**: frozen plans, the executor manifest, the
`LessonPreparationSnapshot` and the receipt chain all work that way. One change of line endings
by the host silently invalidates every downstream piece of evidence, and the error says only
`hash mismatch`. It has recurred three times:

1. the 0.2.2 campaign — a Windows `git clone` rewrote the newlines of historical evidence ->
   the frozen manifest SHA mismatched -> the shadow had to be re-run;
2. 2026-08-06 — a Windows tool converted 83 tracked files from LF to CRLF (`git diff` showed
   25,000 lines; `git diff -w` showed 0);
3. 2026-08-06 — a delivered `.ps1` was saved as UTF-8 without a BOM, and PowerShell 5.1 decoded
   it in the system codepage -> the parse fell apart.

The first two are line endings and the third is character encoding, but the root cause is one:
**the bytes of a deliverable depended on the host's interpretation defaults**.

### 11.2 Repository line endings

`.gitattributes` is the enforcement point, and Main and Skeleton must be byte-identical:

```
* text=auto eol=lf
```

`eol=lf` must be written; `text=auto` alone is not enough. The latter normalizes only the blob,
while **the working tree still follows the host** — and the working-tree file is exactly what
gets hashed. Binary types must be declared explicitly rather than left to auto-detection.

### 11.3 When drift is found

```
git diff HEAD --numstat | wc -l      # files that differ
git diff HEAD -w --numstat | wc -l   # files that still differ ignoring whitespace
```

A `0` for the second means pure line-ending noise: **restore, do not commit**. Committing it
pollutes `git log -S`, blame, and every SHA-bound piece of evidence. After restoring, confirm no
CRLF remains anywhere in the repo — and scan with a reliable implementation: a shell one-liner
with nested quotes once returned empty silently and was misread as "clean".

### 11.4 Cross-host delivery scripts

Any delivery script meant to run on another host (`.ps1`, `.sh`, `.bat`):

1. **pure ASCII**, containing no non-ASCII byte — more thorough than "remember the BOM", because
   then the host codepage has no way in;
2. **LF newlines**;
3. file-hash arguments are **computed at runtime**, never hardcoded (a content fingerprint such
   as a payload SHA may be hardcoded; that does not vary by host);
4. **assert non-empty** after reading a value, before passing it downstream; otherwise an empty
   string is taken as a missing argument and the error points somewhere else entirely;
5. **never assume an external command's failure semantics.** A non-zero exit code is not
   necessarily an error — the check-only path at `sync_lite.py:707` uses `return 1` to mean
   "drift exists, go run `--write`". Read its source or run it once before acting, then
   **assert on the field that actually means something** (`missing=0`, `orphan=0`), rather than
   treating the exit code as the criterion;
6. **a helper that wraps an external command must carry a known-answer probe.** Before doing
   anything real, the function runs one call whose result is known (such as `git --version`), and
   stops immediately if it does not match; nothing downstream may then feed into a judgement.

The price of item 6 is concrete: a wrapper that named a parameter `$Args` (a PowerShell reserved
automatic variable) silently dropped every argument, so `git` printed 40 lines of usage help, and
the caller read those 40 lines as "40 modified files" — the gate then "correctly" blocked a
problem that did not exist. **When a tool fails silently it does not produce an empty value, it
produces plausible-looking fake data**; only once a tool has proved it is working does its output
deserve to count as evidence. This is the same lesson as "scan with a reliable implementation" in
§11.3, in a second location.

> Known PowerShell reserved automatic variables (never use as a parameter name): `$Args`,
> `$Input`, `$Error`, `$Host`, `$PSItem`, `$Matches`, `$This`, `$PID`, `$PWD`.

### 11.5 Consumers

- `activity_close.line_ending_drift()` — on a SHA mismatch, decides whether the difference is
  line endings only, and writes `LINE ENDING DRIFT` directly in the error message, pointing here
  instead of making someone re-run the matrix. Mount points: plan binding, the authorization
  receipt, the post-close hash, and the plan content hash.
- L2 has landed as `release.line_endings` (registered 2026-08-07, running in the release
  profile); L1 remains deferred (adjudicated 2026-08-19, not scheduled). The original plan is
  `docs/handoffs/T2AG_HOST_BYTE_DRIFT_PREVENTION_PLAN_2026-08-06.md` (P-0088 erratum on its
  status line).

> **rule_migration** (§6.3): the §8 row "CRLF/LF warning | usually harmless; do not rewrite the
> whole repository to silence the notice" is judged `retire + replace`. The first half of the old
> wording ("usually harmless") was the permit condition for this class of incident and has been
> falsified; the second half ("do not rewrite the whole repository") is **retained and
> strengthened** as §11.3's "restore, do not commit" — both oppose writing line-ending
> differences into history, and differ only in the direction of the handling. The new owner is
> §11 here; the consumers are `activity_close.line_ending_drift()` and the two pointer rows in
> the §8 error table; verification is that function's positive and negative assertions (a real
> content change must never be judged as drift).
