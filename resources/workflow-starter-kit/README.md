# Nymrel Workflow Starter Kit

Version 0.1.0 · public source preview · MIT licensed

Two reusable agent skills and a reporting template, adapted from workflows we
use at Nymrel. They help answer three practical questions: What do the sources
actually show? Is a new capability worth adopting? What changed since the last
update?

We selected these for usefulness and their ability to work independently. We
have not measured usage frequency, so this is not a most-used ranking.

| Included | What it does | How we use the workflow | Try asking |
| --- | --- | --- | --- |
| [Evidence Workspace](skills/evidence-workspace/SKILL.md) | Creates a source-linked HTML snapshot, Markdown brief, and JSON export; compares two checkpoints. Includes a runnable offline Python renderer. | Reconcile issue/PR state and distinguish source implementation, testing, release, and real use. | “Compare these two checkpoints. What changed, and what is still unverified?” |
| [Capability Adoption](skills/capability-adoption/SKILL.md) | Guides one bounded comparison using primary documentation, a baseline, a pass/fail criterion, and a stop condition. Includes an experiment template. | Evaluate a new AI feature, plugin, or developer tool before recommending adoption. | “Evaluate this tool against our current approach using one synthetic task.” |
| [Material Change Digest](resources/material-change-digest.md) | A short update template with the change, reported responsibility, next action, checkpoint, evidence, and uncertainty. | Make project and agent updates readable while preserving the original evidence. | “Summarize only material changes and link the supporting sources.” |

## Start here

People can read the linked guides and use the templates immediately. Give your
agent the relevant `SKILL.md` and the task you want to complete. In a host that
supports Agent Skills, install the desired skill folder using that host's
documented local-skill mechanism, keeping its scripts, assets, references, and
tests together. Host installation and automatic routing have not been verified
by this source release.

Evidence Workspace also links to the digest at the kit's `resources/` directory.
Keep the whole kit layout when using that optional companion reference.
Capability Adoption has no dependency on the other skill.

The kit needs no Nymrel account, hosted MCP service, app binding, API key, or
subscription. An agent still needs its own authorized tools to retrieve source
records. The renderer processes supplied files locally and does no retrieval.

## Run the synthetic example

Use Python 3.10 or later. From this kit's root directory:

```sh
python skills/evidence-workspace/scripts/evidence_workspace.py validate --input skills/evidence-workspace/references/synthetic-example.json --json-errors
python skills/evidence-workspace/scripts/evidence_workspace.py build --input skills/evidence-workspace/references/synthetic-example.json --audience public --output evidence-example
python -m unittest discover -s skills/evidence-workspace/tests -p 'test_*.py'
```

The output directory must be new. Open `evidence-example/index.html` to inspect
the snapshot; `brief.md` and `view.json` contain the same audience-visible data.
The example is synthetic. The renderer checks input consistency and retains
source links; it does not authenticate those sources or establish that a claim
is true. Supported input adapters are documented in the
[input contract](skills/evidence-workspace/references/input-contract.md).

For a tool evaluation, copy the
[adoption packet](skills/capability-adoption/references/adoption-packet.md) into
your existing project note. Define the comparison before running it. Report
unknown measurements as unknown.

## What this release establishes

This is a public source preview of the skills and offline resources. Its
verification record is in [RELEASE.md](RELEASE.md). It is separate from the
existing Nymrel service and from ChatGPT Directory, package-registry, or
provider-specific publication. A source download is not proof of installation,
host invocation, deployment, or real-world adoption.

Private operating records, personal correspondence, customer data, private
connections, and credentials are excluded. Public export filtering helps exclude
records marked private; it cannot correct a mistaken confidentiality label.
Review the remaining content and sharing authority before publishing an output.

## License and attribution

Copyright (c) 2026 Nymrel. The [MIT license](LICENSE) covers this public edition.
It is adapted from Nymrel's studio workflows, with internal coordination
dependencies removed. No third-party source records are bundled.
