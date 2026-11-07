# Offline local citation check

This independently authored companion is in the public repository under the
workflow starter kit’s MIT license. It is separate from the immutable Workflow
Starter Kit v0.1.0 archive and tag, and contains no private source code.

This standalone Python 3.10+ utility checks explicitly selected local Markdown
bytes and line citations. It does not change the Evidence Workspace input schema,
retrieve URLs, crawl directories, authenticate sources, or establish whether a
claim is true or whether its contents may be shared.

Create a private JSON manifest in the following shape. The digest is lowercase
SHA-256 of the exact file bytes, including their original line endings. Each ID
must be a unique, randomly generated 32-character lowercase hexadecimal token;
do not encode names or other private information in it. Use your normal secure
random generator, for example Python's `secrets.token_hex(16)`.

```json
{"citations":[{"id":"0123456789abcdef0123456789abcdef","path":"notes/example.md","sha256":"<64 lowercase hex characters>","start":1,"end":2,"quote":"optional exact text"}]}
```

The illustrative digest must be replaced with the digest of the selected file.
`start` and `end` are inclusive one-based line numbers; `quote` is optional and,
when present, must occur in the selected lines. For quote matching, LF and CRLF
line endings become LF. Hashing always uses the unchanged bytes. Invalid UTF-8,
a missing file, invalid range, absent quote, or symlink yields `unresolved`; a
hash mismatch yields `changed`. Only matching bytes and a valid selected range
(and quote, if supplied) yield `verified`. An empty quote is invalid.

From the repository root, select each permitted root-relative `.md` path
explicitly; repeat `--allow` for multiple files:

```sh
python resources/local-citation-check/scripts/verify_citations.py --root /path/to/source --input /path/to/private-manifest.json --allow notes/example.md
```

Manifest paths must match the allowlist exactly. Absolute paths, traversal,
backslashes, colons (including Windows drive and stream syntax), extra fields, duplicate IDs, and duplicate JSON object keys are
rejected. The manifest may hold sensitive paths and quotations; keep it private.
The JSON output contains only opaque IDs and statuses; diagnostics contain no
file names, source content, or quotations. Review IDs and output before sharing;
the tool cannot determine sharing rights or whether an ID is truly random.
Exit 0 means every citation verified, 1 means at least one changed or unresolved,
and 2 means invalid/unreadable input with no results. Source files are limited to
2 MiB, the manifest to 1 MiB and 100 citations. No source files are written.

Use a source directory controlled by the operator and not being modified by
other processes while checking. Symlink components are refused, but this tool
is not a sandbox against a hostile process racing filesystem changes. Results
are a point-in-time consistency check, not source authenticity or authority.

Run the focused tests from the repository root:

```sh
python -m unittest discover -s test/release -p 'test_verify_local_citations.py'
```
