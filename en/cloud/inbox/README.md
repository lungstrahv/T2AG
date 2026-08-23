# The cloud handoff inbox

Save a `CH-YYYYMMDD-NNNN.md` returned by the cloud into this directory verbatim.

- Receiving is not accepting; the initial status must be `proposed_for_local_review`.
- First check the source `directive_id`, the actual changes, the deviations, the verification, the open
  questions, and the privacy impact.
- Only after discussing with the user is the accepted part written locally and doctor run.
- The cloud's original handoff is never rewritten; the local adjudication is recorded in
  `../cloud_sync_state.md`.
