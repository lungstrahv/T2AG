# Access and state authority

Decision: mobile access normally controls the same running T2AG instance. An
independent cloud classroom is an optional exchange mode, used only when the
teaching environment cannot access that instance. Device type and model hosting
location do not determine learning-state authority.

| Situation | Authority and execution | T2AG behavior |
|---|---|---|
| Desktop or mobile controlling the same host | One instance and journal; actions execute on that host | Use normal context, named actions, receipts and checks. No mirror, event export or sync ceremony. |
| Another task connected to the same instance | Same journal, potentially different session and stale context | Read current object versions. Preserve session-bound permissions and reject stale decisions. A second task does not inherit the first task's teaching permission. |
| Independent cloud or offline conversation | Read-only exported baseline plus unsynchronized new evidence | Explicitly enable compatibility exchange; retain originals, deduplicate and reconcile before local application. |
| Host unavailable or connection uncertain | Local result is unknown to the client | Report the uncertainty. Reconnect and look up the original request; do not start an independent classroom automatically. |

## Shared-instance path

```text
Desktop interface ─┐
                  ├──→ authorized host task ─→ T2AG instance ─→ durable receipt
Mobile interface ─┘                            one journal

Connection lost ─→ reconnect ─→ lookup original request
                                  ├─ committed: show receipt
                                  ├─ absent: retry unchanged request
                                  └─ integrity error: retain evidence and diagnose
```

Remote transport, host login, device pairing and operating-system permissions
belong to the selected host product. T2AG does not build another remote-control
server or mistake a caller-supplied device label for authenticated access.
Keeping the same conversation on another screen does not force a new teaching
session. Starting a distinct host conversation does not resurrect an old scan or
permission ticket.

For the common path, the learner says which course to continue and receives its
actual pending question or confirmation. They do not copy protocol blocks merely
because they changed screens. Normal saves retain the same atomicity,
idempotency, version checks and applicable teaching conditions.

## Compatibility path

T2AG-CLOUD-1 remains a compatibility contract for actual independent teaching
and historical imports. Its teaching-event and component-proposal channels stay
separate. A saved offline event is not a local commit; a received component
proposal does not automatically modify local rules. Existing paused exchange
stays paused, and old private identity fields are not published in templates.

Enabling compatibility must be explicit and scoped. It is not inferred from a
mobile user agent, a new chat, a network error, or the fact that model inference
uses a cloud service. A disabled compatibility path and missing cloud mirror
must not prevent local or shared-instance teaching or require irrelevant sync
checks.

## Acceptance evidence still required

Run cross-process continuation, duplicate-request recovery, stale concurrent
decisions, interrupted-response lookup, and cold new-conversation recovery
against one actual journal. Test independent exchange separately. Deterministic
local tests are not proof of successful pairing, phone usability, remote network
latency or continuity on a particular host product; report those measurements
only when actually exercised.

## Rationale and sources

The 2026-09-30 user correction changes the default access path while retaining
the original ability to learn in an independent environment. Official documents
were checked on 2026-10-01 UTC: [Codex remote connections](https://learn.chatgpt.com/docs/remote-connections)
and [Claude Code Remote Control](https://code.claude.com/docs/en/remote-control)
describe mobile access to tasks running on a host machine. Availability on a
specific account or computer is a deployment question, not an assumption in the
T2AG data model.
