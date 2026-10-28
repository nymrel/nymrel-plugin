# Nymrel MCP Preflight — validation prototype

A small offline experiment for developers and technical support staff: read a
supplied MCP configuration and optional log, then produce an understandable
diagnostic report without starting the server.

**Product demand is not validated.** This is a candidate to compare with the
existing [MCP Inspector](https://github.com/modelcontextprotocol/inspector),
which already provides extensive interactive and command-line diagnostics.
The goal is to test whether a conservative, shareable explanation saves time
on a few concrete setup failures.

## First run

Python 3.10 or later; standard library only. From this directory:

```sh
python preflight.py --config fixtures/package-runner.json --log fixtures/setup.log --output example-report
python -m unittest discover -s tests -p 'test_*.py'
```

Use a new output directory. Open `example-report/index.html` or read
`example-report/report.json`. The fixture is synthetic; it is not a reproduction
of an upstream issue or evidence about a production service.

The optional `--check-local-runtimes` checks the current machine's PATH for a
small allowlist of runtime launchers. It does not execute them or establish
which runtimes are available in a different deployment.

## What it checks

The supported input shapes are a `mcpServers` object or a VS Code-style
`servers` object, with at most 100 entries and a 2 MiB limit per input file.
JSON numeric literals are limited to 1,000 characters; nonfinite numbers and
duplicate keys are rejected. A recognized package pin uses a simple numeric
`x.y.z` version. Other valid version syntaxes remain unconfirmed by this limited
checker rather than being declared unpinned.
Rules look for package-runner installation/egress possibilities,
some unconfirmed package version pins, disabled certificate checks, and selected
log signals for runtime, certificate, registry, timeout, or protocol-output
problems. Unsupported shapes and unmatched cases remain unverified.

The report contains fixed explanations and ordinal server identifiers. It does
not echo server names, command arguments, environment values, endpoints, raw log
lines, or input paths. Review any report before sharing it. The tool reads local
files and writes the requested report; it starts no subprocess, makes no network
request, installs nothing, and changes no configuration or credentials.

## Important limits

- Configuration inspection cannot discover every dependency or network request
  hidden inside a package. A pinned launcher package does not prove all code
  that later executes is pinned.
- Log patterns are clues, not causal proof. Combined logs do not establish that
  a message was emitted on stdout rather than stderr.
- A generic timeout cannot identify whether startup, HTTP, parsing, or response
  delivery failed without additional evidence.
- No matches means **not verified**, never ready, safe, authenticated, or secure.
- Exit zero means analysis completed. It is not a release or security gate.
- This prototype is not a sandbox, credential scanner, live health check, MCP
  client, package audit, or replacement for Inspector.

## Evidence behind the experiment

Two open upstream reports describe different parts of this troubleshooting job:

- [servers #4199](https://github.com/modelcontextprotocol/servers/issues/4199):
  a reporter attributes a timeout to a synchronous Node-based extraction step.
  A later triage comment says the behavior remains on v2 and awaits review.
- [servers #4830](https://github.com/modelcontextprotocol/servers/issues/4830):
  reports installation traffic inside a tool call and possible protocol-output
  interference; a separate commenter reports similar registry access.

These are source reports and triage assertions, not our reproductions. The
upstream repository currently accepts issues rather than outside pull requests,
according to its triage comments. Respect its current contribution policy.

Broader motivation: the [2026 Stack Overflow AI survey](https://survey.stackoverflow.co/2026/ai/)
describes trust conditioned on easy validation and output quality as the largest
reported reason for switching AI tools. That supports investigating verification
and diagnosis; it does not establish demand for this particular product.

## Decide whether to continue

Follow the [validation protocol](../research/VALIDATION.md) in the complete
discovery bundle. Compare the same broken setup cases with the current Inspector
and normal documentation before recommending adoption. Stop if the existing
tools solve the tasks equally well, if diagnoses mislead users, or if no one
returns with a second useful case.

The prototype has not been tested with outside users, published to a registry,
installed in a supported host, or connected to any Nymrel service. See the
discovery bundle's verification receipt for tests actually run.

The [pilot pack](validation/README.md) adds five synthetic scenarios, neutral
participant task cards, and blank observation templates. Its first planned
human comparison is supplied-file diagnosis against current documentation;
Inspector's live diagnostics are not evaluated by that comparison. Run the
offline scenarios with `python validation/run_scenarios.py --output NEW_DIR`.

Copyright (c) 2026 Nymrel. [MIT licensed](LICENSE).
