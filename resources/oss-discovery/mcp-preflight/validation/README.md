# Offline pilot preparation

This pack executes five synthetic diagnostic scenarios against the unchanged
preflight core. It checks that known clues remain useful and missing evidence
stays uncertain. It does not run MCP Inspector, any server, package, network
request, participant study, or model evaluation.

From the prototype directory:

```sh
python validation/run_scenarios.py --output NEW_RESULT_DIRECTORY
python -m unittest discover -s tests -p 'test_*.py'
```

`NEW_RESULT_DIRECTORY` must not exist and its parent must be writable. Exit 0
means the declared synthetic checks passed, exit 1 means a declared check
failed, and exit 2 means the inputs or output path were invalid. A pass is not
a connection, security, readiness, adoption, or market-validation result.

The output contains `result.json`, a readable `index.html`, and minimized
reports for each case. Raw configurations, names, arguments, values, endpoints,
input paths, and log lines are not copied into those outputs. The synthetic
input cases remain in this source pack. No local-runtime lookup is requested.

## Human comparison remains separate

Use [TASK_CARDS.md](TASK_CARDS.md) with five consenting participants under the
owning study protocol. This first study is explicitly a **supplied-file/
documentation comparison**. Record the current MCP Inspector documentation
revision, and record an actual tool version only if it was separately used.
Inspector's live diagnostics are outside this phase; these results cannot
establish superiority over those capabilities. No upstream package should be
run for these supplied-file tasks, and no held service should be contacted.

Share only the neutral `participant-cases/` files and task cards with
participants. Retain this facilitator mapping and the machine expectations:
**A = missing-runtime; B = installer-streams; C = certificate-egress;
D = hidden-dependency-unknown; E = no-signal.** Do not give participants the
diagnosis-named source files, `cases.json`, or answer key before their response.

The hardest case has a fictional pinned Python package and a hidden nested
dependency. Only a generic timeout is supplied. Correct behavior is to request
stage-specific evidence; the prototype cannot discover the hidden dependency
from that configuration. Do not present all cases as solvable by a rule match.

[observations-template.json](observations-template.json) and
[observations-template.csv](observations-template.csv) are blank collection
templates. Participant count, time, accuracy, and repeat use are unknown until
actual consented observations exist. Do not publish identifying information or
fill the templates with agent-generated participants.

Retain the participant's actual proposed next action, self-reported confidence,
task order, fixture revision, baseline documentation revision, and assistance
alongside any correctness judgment. A checkbox alone is insufficient evidence
for diagnosis quality.

The case manifest is strict, requires all five defined cases, and rejects
inconsistent expectations and file references escaping the case pack. Its
result checks are bounded contracts for these fixtures, not a general-purpose
truth or safety classifier.
