# Release the Workflow Starter Kit source preview

This route publishes the existing standalone kit ZIP and its SHA-256 file as a
GitHub prerelease. It does not deploy the MCP service, change the installed
Nymrel plugin, or publish to a directory or package registry.

Before tagging, review and merge the candidate normally, including current
contract CI, CodeQL, and the source-preview release verification matrix. The
version in the kit README, archive filename, archive paths, and release tag must
agree. Preserve published archives and tags; use a new version for changed bytes.

For the current kit, tag the reviewed integrated revision as
`workflow-starter-kit-v0.1.0`, then push that tag through the authorized repository
route. Tag publication runs the Python 3.10/3.13 checks, confirms main ancestry,
and compares every archive entry against tracked source before granting the
publication job `contents: write`. The ZIP is uploaded unchanged, never rebuilt.

Pull requests and main pushes run verification only. The publication job uses
GitHub's built-in token and `gh release create --verify-tag --prerelease`; it
cannot replace an existing release or move a tag. If a release creation or asset
upload fails, inspect the existing release and its assets before recovery.
Do not delete, overwrite, or republish an uncertain result automatically.

After success, read back the GitHub release's tag and assets, download both
assets, check the SHA-256, and exercise the synthetic example from the downloaded
kit. A successful workflow alone is not a claim about host installation, model
routing, customer use, or service availability.
