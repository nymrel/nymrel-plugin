# Security policy

Report vulnerabilities privately to `contact@nymrel.com`. Do not publish
credentials, private handoff content, personal data, or working exploit
payloads in a public issue. Include the affected commit or route, expected and
observed behavior, impact, and the smallest safe reproduction.

The maintained source is the current `main` branch. The reviewed runtime lines
are Node 22 and 24 for the local TypeScript harness and Python 3.13 for the
hosted MCP service. Activation-held private tools are not considered public
until their separate provider, consent, storage, tester, and production canary
gates have passed.

We validate corrections with the complete local gate, dependency audits,
CodeQL when hosted Actions is available, and target-client canaries where the
boundary requires them. A merged source fix does not by itself prove a
production deployment or third-party directory update.
