# Synthetic task cards

These tasks use fictional configuration/log files. No server or package needs to
be run. Do not enter real credentials, use a production endpoint, or reconnect a
held service. The files contain obvious synthetic sentinels, not real secrets.

For every task, answer: What does the supplied evidence establish? What remains
unknown? What is the next defensible action? Explain your confidence. The task
is complete when you can state a next action or explain why narrower evidence
is needed; a guessed fix is not required.

1. **Case A.** Use `participant-cases/A.config.json` and `A.log`. You are
   helping a colleague understand a failed tool request.
2. **Case B.** Use `participant-cases/B.config.json` and `B.log`. The operator
   captured stdout and stderr together. Explain what the evidence establishes
   and the next evidence you would collect.
3. **Case C.** Use `participant-cases/C.config.json` and `C.log`. You may
   inspect the supplied evidence and approved documentation. Changing settings
   is outside the task.
4. **Case D.** Use `participant-cases/D.config.json` and `D.log`. The fictional
   Python package was pinned at installation time. Explain what the supplied
   evidence establishes and the next evidence you would collect.
5. **Case E.** Use `participant-cases/E.config.json` and `E.log`. Explain what
   the supplied evidence establishes and the next evidence you would collect.

This first comparison is a **supplied-file/documentation comparison**. It does
not evaluate live Inspector diagnostics. The facilitator should retain the
mapping and answer key in `README.md`; share these tasks and the neutral case
inputs without the answer key or source folders. Use current documentation as
a baseline and record its revision.
Alternate baseline/prototype order across consenting participants. No baseline
execution, participant comparison, or measured savings is recorded here.
