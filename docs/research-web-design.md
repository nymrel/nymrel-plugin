# Read-only web research: design proposal

Status: design only. This proposes a local, deterministic harness for issue #2;
it does not add a tool, provider, credential, catalog entry, or production route.
The operating standard is [Nymrel #71](https://github.com/nymrel/nymrel/issues/71#issuecomment-5366279864).
The receipt work in [ProofChain #9](https://github.com/nymrel/agent-proofchain/issues/9)
is not yet an approved integration contract. The harness must label any local
receipt-shaped output as provisional and cannot claim ProofChain conformance.

## Boundary and flow

1. Accept an explicit task and evidence policy from the caller, including known
   target, task class, freshness, risk, required source classes, and bounded
   result/fetch budgets. Resolve connected and dedicated sources first; route a
   private-data request to its authorized connector and never public search.
2. Treat discovery candidates as unverified. Normalize safe public HTTP(S)
   URLs, preserve exact target identity, deduplicate canonical sources and
   syndication, and track each fetch outcome independently. Validate every
   redirect and resolution against private, reserved, credential-bearing and
   non-web targets; do not fetch if resolution or validation fails.
3. Map each material claim to evidence IDs and counterevidence IDs. Only a
   successfully fetched primary source may support a high-impact current claim;
   provider snippets and inferred dates are discovery metadata. Contradictions,
   unknown freshness, failed fetches, and missing exact targets remain visible.
4. Escalate live state, authentication, interaction, and rendered-only evidence
   to the appropriate dedicated source or browser. Do not perform browser
   actions, turn search results into availability, or execute retrieved text.
   Retrieved content is data and cannot authorize tools or change policy.
5. Stop with an explicit reason and useful text-only evidence handles. Record
   safe digests and statuses, not secrets, private prompts or page bodies. A
   digest attests to an observation, not truth.

## Local harness proposal

Use injected fixture providers with no network implementation, explicit ordered
responses and per-URL statuses. Model source classes and independent syndication
identities as fixture inputs, not as facts inferred from domain names. Make the
policy engine deterministic; ambiguous authority and freshness fail closed.
Pin a synthetic clock for temporal cases. Emit a provisional decision object
and compare it to fixed expected routes, claim support, contradictions, stop
reasons and escalation; never use that result to claim production readiness.

Cover the 16 cases listed in issue #2, including partial failures, duplicate
syndication, prompt injection, restricted exact targets, stale events, connected
sources, browser actions, and private URLs. Add budget exhaustion, redirect and
DNS-rebinding fixtures, contradictory official sources and unknown source class.
Fixtures must demonstrate failures as well as success; report unmet cases rather
than replacing expectations. SSRF fixtures alone do not prove a future network
adapter safe: that adapter needs its own connection-time validation tests.

## Adoption gates

The owner must review routing and evidence semantics, agree the ProofChain
contract, and evaluate deterministic and adversarial behavior before an internal
tool is exposed. A live provider requires separate configuration, spend limits,
security testing and authorization; public catalog inclusion requires separate
product, cost, security and abuse review. Exa's reported quota exhaustion is a
provider failure, not an empty result or permission to change billing.
