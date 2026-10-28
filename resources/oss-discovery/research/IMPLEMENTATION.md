# Implementation and validation sequence

This source candidate continues the research and prototype in this bundle. It
is an experimental workflow, with demand and comparative usefulness unverified.

| Work | Deliverable | Completion criterion | Current disposition |
| --- | --- | --- | --- |
| Source preparation | Offline diagnostic core, license, examples and supported-input limits | Deterministic tests, private-safe output, independent final-source review | Core built and locally reviewed; candidate checks cover the final tree |
| Pilot preparation | Five synthetic scenarios, task cards, baseline instructions and blank paired-observation template | Scenarios run locally; ambiguous inputs retain uncertainty; no fabricated participants or metrics | Executed separately from a human study |
| Human comparison | Same tasks with current Inspector/documentation and this candidate | Consenting participants, exact versions, observed correctness/time and repeat cases | Not run |
| Human and agent usability | Understandable report/next action and clear machine-readable errors/results | Actual human/host evidence distinct from synthetic checks | Browser checks exist; outside acceptance pending |
| Release readiness | Exact reviewed source, archive, focused checks and containing-repository gates | Normal guarded integration; no audit/review waiver | Source preview and full integration remain separate |
| Distribution | Source-bound demo, supported claims, first-value event and measurement packet | Truthful evidence plus the owning publication process | Prepared draft; no outreach or campaign claimed |
| Adoption decision | Adopt, revise, contribute upstream, or stop | Comparison and repeat-use evidence from the declared protocol | Pending |

The original [Workflow Starter Kit PR #60](https://github.com/nymrel/nymrel-plugin/pull/60)
retains its source and release scope. This sibling candidate does not change its
archive, manifests, or dependency-owner branches. Containing-repository checks
apply to integration even when the offline resource's focused checks pass.

## Execute locally

Follow [the diagnostic README](../mcp-preflight/README.md) from this bundle's
root. The validation directory contains the scenario runner and pilot materials;
follow its own README for the exact invocation and observation fields. Run the
unit suite and scenario checks on the final source before distributing a package.

Results from deterministic fixtures are not model benchmarks, human task-time
measurements, product-market fit, or proof of a real connection. Keep those
outcomes explicitly missing until their actual evidence exists.

## Decision and maintenance

Use [VALIDATION.md](VALIDATION.md) for the comparison gate. Keep existing tools
available to participants; do not hide an incumbent feature or compare with an
obsolete release. An equally useful incumbent or a narrow upstream fix can be
a reason to stop the standalone product.

If the comparison supports continuation, publish one small supported workflow
with a reproducible install, useful example, documented limits, issue handling,
and a sustainable maintenance expectation. Use actual task completion and repeat
use as primary evidence; report downloads and stars as distribution indicators.
Expand scope only when recurring user cases justify it.
