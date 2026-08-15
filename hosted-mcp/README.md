# Nymrel hosted MCP

Production source for `https://mcp.nymrel.com/mcp`.

The public server intentionally exposes four credential-free read tools:

- `nymrel_audit_website`
- `nymrel_find_domain`
- `nymrel_golf_bag_gap`
- `nymrel_social_clip_score`

The vendored client contains additional Nymrel API contracts, but the hosted entrypoint removes them from `tools/list` until their provider or authorization boundaries are production-ready.

## Verify

```powershell
python -m unittest discover -s tests -v
```

## Deploy

Link this directory to the existing `nymrel-mcp` Vercel project, run the tests, then deploy from this exact clean commit. Verify `tools/list` and one successful call per advertised tool after the production alias is ready.
