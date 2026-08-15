---
name: nymrel-website-audit
description: Audit a public webpage with Nymrel and turn the results into a short, trustworthy fix plan for developers or non-developers.
---

# Nymrel Website Audit

Use this workflow when someone asks to audit, check, improve, or understand the technical visibility of a public webpage.

1. Identify the exact public page URL. If no URL is present, ask for one instead of guessing.
2. Call `nymrel_audit_website` with that URL.
3. Preserve the measured scores, evidence, and limitations returned by the tool.
4. Answer at the user’s altitude:
   - For non-developers, explain the top three priorities in plain language and describe the practical outcome.
   - For developers, include the finding IDs, observed evidence, and concrete implementation guidance.
5. Say that the audit is a point-in-time automated technical check. Do not describe it as a legal, accessibility, security, ranking, or compliance certification.

Safety boundaries:

- Audit only public HTTP(S) pages.
- Never ask for passwords, session cookies, API keys, or private-network access.
- If Nymrel blocks a local/private/reserved target, explain the boundary and request a public URL.
- Do not claim that a missing optional signal alone proves a ranking or AI-discovery problem.
