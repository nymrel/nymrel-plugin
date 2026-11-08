import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / "resources" / "local-citation-check" / "scripts" / "verify_citations.py"
ID = "0123456789abcdef0123456789abcdef"


class CitationCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "source"
        self.root.mkdir()
        self.source = self.root / "note.md"
        self.data = b"alpha\r\nbeta gamma\r\n"
        self.source.write_bytes(self.data)
        self.manifest = Path(self.temp.name) / "private.json"
        self.item = {"id": ID, "path": "note.md", "sha256": hashlib.sha256(self.data).hexdigest(), "start": 2, "end": 2, "quote": "beta gamma"}

    def run_cli(self, items=None, allow="note.md", raw=None):
        self.manifest.write_text(raw if raw is not None else json.dumps({"citations": items if items is not None else [self.item]}), encoding="utf-8")
        return subprocess.run([sys.executable, str(SCRIPT), "--root", str(self.root), "--input", str(self.manifest), "--allow", allow], text=True, capture_output=True)

    def status(self, result):
        self.assertEqual(result.stderr, "")
        self.assertNotIn(str(self.root), result.stdout)
        self.assertNotIn("note.md", result.stdout)
        self.assertNotIn("beta gamma", result.stdout)
        return json.loads(result.stdout)["citations"][0]["status"]

    def test_valid_crlf_exact_bytes_and_quote(self):
        result = self.run_cli()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.status(result), "verified")

    def test_changed_bytes_fail_closed(self):
        self.source.write_bytes(self.data.replace(b"\r\n", b"\n"))
        result = self.run_cli()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.status(result), "changed")

    def test_missing_invalid_utf8_range_and_quote_unresolved(self):
        self.source.unlink()
        self.assertEqual(self.status(self.run_cli()), "unresolved")
        self.source.write_bytes(b"\xff")
        self.item["sha256"] = hashlib.sha256(b"\xff").hexdigest()
        self.assertEqual(self.status(self.run_cli()), "unresolved")
        self.source.write_bytes(self.data)
        self.item["sha256"] = hashlib.sha256(self.data).hexdigest()
        self.item["end"] = 3
        self.assertEqual(self.status(self.run_cli()), "unresolved")
        self.item.update(end=2, quote="absent")
        self.assertEqual(self.status(self.run_cli()), "unresolved")

    def test_reject_unselected_traversal_duplicate_and_unknown(self):
        for mutation in ({"path": "other.md"}, {"path": "../secret.md"}, {"surprise": "secret"}):
            item = dict(self.item, **mutation)
            result = self.run_cli([item])
            self.assertEqual((result.returncode, result.stdout), (2, ""))
            self.assertNotIn("secret", result.stderr)
        result = self.run_cli([self.item, self.item])
        self.assertEqual((result.returncode, result.stdout), (2, ""))
        result = self.run_cli(raw='{"citations": [], "citations": []}')
        self.assertEqual((result.returncode, result.stdout), (2, ""))

    def test_windows_drive_and_alternate_stream_paths_rejected(self):
        for path in ("C:/secret.md", "C:secret.md", "notes:secret.md"):
            with self.subTest(path=path):
                result = self.run_cli([dict(self.item, path=path)], allow=path)
                self.assertEqual((result.returncode, result.stdout), (2, ""))
                self.assertNotIn(path, result.stderr)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_symlink_source_refused(self):
        self.source.unlink()
        try:
            self.source.symlink_to(Path(self.temp.name) / "outside.md")
        except OSError:
            self.skipTest("symlink creation unavailable")
        result = self.run_cli()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.status(result), "unresolved")


if __name__ == "__main__":
    unittest.main()
