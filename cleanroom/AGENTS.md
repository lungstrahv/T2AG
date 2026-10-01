# T2AG agent entry

Read `docs/protocol.md` before acting. Use the student's chosen language and explain directly when that helps; T2AG also supports practice, projects, real-world reflection, planning and governance. It is not restricted to asking questions.

Apply the returned presentation and collaboration preferences in the response.
Hiding an optional display does not remove its saved evidence or a necessary
learning decision. Course bindings carry execution routines and evidence only;
they do not award mastery, settle course work or consume a group's time budget.

For a common task, read its short loop with `python -m t2ag_next workflow <name> --language <zh|en>`; omit the name to list the six choices. See `docs/task-loops.md`. Reuse a loop already read in this conversation. Its steps guide the task, not a mandatory tool-call count; finish when its outcome is reached.

This directory is a portable runtime. `installation.json` identifies the edition and instance path; if `instance_path` is absent, use `instance/`. Treat an external instance path as data, not a shell command. Read the JSON with a JSON parser. Never infer progress from the runtime's file timestamps.

Mobile remote control of this host uses the same instance and ordinary actions. Do not create another cloud progress store, demand a pasted sync block, or run cloud checks merely because the interface is a phone. On reconnect, look up an uncertain original request before retrying. Independent offline teaching requires explicit compatibility exchange; see `docs/access-authority.md`. Host access is not permission to advance a teaching gate.

1. Declare both entry (`entry.teach`, `entry.maintain`, `entry.audit`, or `entry.release`) and session lane (`teach`, `maintain`, `audit`, or `release`) from the actual task. These axes may differ. Maintenance and review do not restore a lesson automatically.
2. Run `python -m t2ag_next --instance <path> context --entry <entry> --lane <lane> --scope <course>`. Teaching needs a named course. Add the current session ID only if it actually exists. Expand L1/L2 or `inspect <kind> <id>` only for needed evidence. Load the referenced teacher, overlay and skin once per version before teaching; reuse unchanged content already in this conversation. A save or close does not require rereading presentation templates. Pointers are not evidence already read.
3. On a new instance, collect only optional facts the learner supplies; keep absent facts unknown. Show a complete editable learning proposal and obtain its explicit confirmation before activation. Do not invent a plan acceptance, course, textbook reading or historical permission.
4. Use named actions listed by `actions`. The request includes a stable request ID, the actual actor statement/reference, exact payload and versions of read dependencies. Send a UTF-8 JSON file with `act`; duplicate JSON keys and nonfinite values are rejected. Keep the original request when resolving an uncertain save.
5. Give teaching feedback as soon as its evidence is clear. An understanding assessment can preserve the answer, frozen criterion, judgment and cursor in one `comprehension.assess` transaction. State whether saving is pending, committed, rejected or unknown. For an uncertain result, `lookup <original-request-id>` before retrying the identical request.
6. Respect the returned current question, pending body, feelings gate and next-block permission. A correct answer or a save request does not authorize moving on. Textbook teaching requires the current session's actual page consumption. `evidence` reads immutable blob bytes with content verification; metadata inspection alone is not page reading.
7. Domain checks run on relevant changes. Full `doctor --full` belongs at import, integrity investigation and release gates, not every simple answer. Derived views can be rebuilt with `state --write`; they never replace journal facts.

Public packages contain no personal instance or source book. Installations, migration imports and upgrades retain previous data and use new destinations. Choose the Chinese or English user guide for the learner's overview. This protocol describes attribution and host limitations honestly; it is not a claim of cryptographic proof of human consent or complete adversarial enforcement.
