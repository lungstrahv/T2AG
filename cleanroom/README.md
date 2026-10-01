# T2AG 0.3 cleanroom candidate

T2AG combines source-based teaching, practice, exact learning recovery, course planning and evidence-based system maintenance. The teacher explains and illustrates content, responds to the learner, and records what actually happened. A correct answer, permission to continue, a saved record and course completion remain separate facts.

This repository is an executable reconstruction candidate. Final full-function equivalence, real-data cutover and release qualification remain subject to the coverage matrix and non-author reviews. Existing classroom instances continue in their original location during development.

Use Python 3.11 or newer. The core needs only the standard library:

```console
python -m t2ag_next --instance ./instance init --language zh
python -m t2ag_next --instance ./instance context --entry entry.maintain --lane maintain
python -m t2ag_next actions
python -m unittest discover -s tests
```

Select the edition explicitly. The learner communicates naturally with their agent; the agent uses the commands and retains actual statements rather than inventing consent. Requests are UTF-8 JSON files submitted with `act`. Successful receipts mean the journal was durably published under the documented filesystem guarantees. An unknown result must be resolved using the original request ID.

PDF rendering uses the optional `pdf` extra; OKF export and validation use the
optional `okf` extra. Install the needed extra with `pip install .[pdf]` or
`pip install .[okf]`. Ordinary learning records require neither dependency.

- [中文使用指南](docs/user-guide.zh.md)
- [English guide](docs/user-guide.en.md)
- [Operating protocol](docs/protocol.md)
- [Domain model](docs/domain-model.md)

Instances, source books and personal history are separate from the runtime distribution. Installation never merges with an existing destination. A migration archive preserves bytes; usable migration additionally requires mapped state, reachable evidence and successful recovery. Neither packaging nor installation authorizes deleting the original instance.
