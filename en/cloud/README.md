# T2AG cloud bridge directory

> **What lives here**: the bridge files between local and cloud (mobile / web) —
> prompts, sync state, handoff artifacts.
> **Who writes, who reads**: written during cloud sync; read during local takeover.
> **When you come here**: when something learned on mobile must sync back to
> local, or local must push a component change to the cloud.

This directory holds the cloud runtime prompt and the bidirectional sync
credentials. It replaces no course or rule source of truth in `main/`.

```text
cloud/
├── T2AG_PROJECT_INSTRUCTIONS.txt
├── cloud_sync_state.md
├── outbox/   # component change directives sent from local to cloud
└── inbox/    # handoff files returned by cloud, awaiting local discussion
```

## Two sync channels

- Teaching state: cloud emits `T2AG_SESSION_CLOSE`; local validates and writes
  back to the course files.
- Component change: local emits `T2AG_CLOUD_CHANGE_DIRECTIVE`; cloud modifies or
  proposes and returns `T2AG_CLOUD_HANDOFF`; local adjudicates after discussing
  with the user.

A directive file in state `ready_to_send` is **not** the same as sent: marking it
`sent` requires upload-tool evidence or user confirmation. A cloud handoff always
begins at `proposed_for_local_review` and never becomes a local rule
automatically.

When establishing or changing the sync architecture for the first time, send
three items: the protocol definition source `cloud_learning_sync.md`, the Project
Instructions execution projection, and the corresponding `CD-*.md` directive.
Ordinary teaching uses only the Project Instructions and existing project
material; there is no need to resend the protocol every lesson.
