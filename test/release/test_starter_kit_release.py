"""Exercise release rejection boundaries using a disposable Git repository."""

import hashlib
import importlib.util
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("release_check", ROOT / "scripts/verify-starter-kit-release.py")
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)
TAG = "workflow-starter-kit-v0.1.0"


class ReleaseBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        # Copy tracked bytes only; an earlier test run may leave ignored caches.
        for name in CHECK.git(ROOT, "ls-files", "-z", "--", str(CHECK.KIT_PATH)).split("\0"):
            if name:
                destination = self.root / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / name, destination)
        shutil.copytree(ROOT / "resources/releases", self.root / "resources/releases")
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(["git", "-C", str(self.root), "add", "resources"], check=True)
        self.archive = self.root / "resources/releases/nymrel-workflow-starter-kit-0.1.0.zip"

    def rewrite(self, transform):
        with zipfile.ZipFile(self.archive) as source:
            entries = [(item, source.read(item)) for item in source.infolist()]
        with zipfile.ZipFile(self.archive, "w") as target:
            for item, content in transform(entries):
                target.writestr(item, content)
        self.archive.with_suffix(".zip.sha256").write_text(
            f"{hashlib.sha256(self.archive.read_bytes()).hexdigest()}  {self.archive.name}\n", encoding="utf-8")

    def test_accepts_exact_existing_archive(self):
        self.assertEqual(CHECK.verify_archive(self.root, TAG)[0], self.archive)

    def test_rejects_wrong_tag_and_version(self):
        for tag in ("v0.1.0", "workflow-starter-kit-v0.2.0", "workflow-starter-kit-v00.1.0"):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                CHECK.verify_archive(self.root, tag)

    def test_rejects_checksum_tamper(self):
        with self.archive.open("ab") as output:
            output.write(b"tamper")
        with self.assertRaisesRegex(ValueError, "checksum"):
            CHECK.verify_archive(self.root, TAG)

    def test_rejects_source_drift(self):
        (self.root / CHECK.KIT_PATH / "README.md").write_text("Version 0.1.0 · changed\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "differs from source"):
            CHECK.verify_archive(self.root, TAG)

    def test_rejects_modified_archive_with_updated_checksum(self):
        def change(entries):
            first, *rest = entries
            return [(first[0], b"changed")] + rest
        self.rewrite(change)
        with self.assertRaisesRegex(ValueError, "differs from source"):
            CHECK.verify_archive(self.root, TAG)

    def test_rejects_extra_traversal_and_duplicate_paths(self):
        for name in ("extra", "../outside", "nymrel-workflow-starter-kit-0.1.0/LICENSE"):
            with self.subTest(name=name):
                original = self.archive.read_bytes()
                try:
                    self.rewrite(lambda entries: entries + [(name, b"unexpected")])
                    with self.assertRaisesRegex(ValueError, "paths"):
                        CHECK.verify_archive(self.root, TAG)
                finally:
                    self.archive.write_bytes(original)

    def test_rejects_symlink_entry(self):
        def symlink(entries):
            entries[0][0].external_attr = (stat.S_IFLNK | 0o777) << 16
            return entries
        self.rewrite(symlink)
        with self.assertRaisesRegex(ValueError, "regular files"):
            CHECK.verify_archive(self.root, TAG)

    def test_source_identity_and_main_ancestry(self):
        subprocess.run(["git", "-C", str(self.root), "-c", "user.name=Release Test",
                        "-c", "user.email=release@example.test", "commit", "-qm", "Accepted source"], check=True)
        accepted = CHECK.git(self.root, "rev-parse", "HEAD")
        subprocess.run(["git", "-C", str(self.root), "update-ref", "refs/remotes/origin/main", accepted], check=True)
        CHECK.verify_source(self.root, accepted)
        with self.assertRaisesRegex(ValueError, "does not match"):
            CHECK.verify_source(self.root, "0" * 40)
        (self.root / CHECK.KIT_PATH / "LICENSE").write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "tracked source changes"):
            CHECK.verify_source(self.root, accepted)
        subprocess.run(["git", "-C", str(self.root), "add", "resources"], check=True)
        subprocess.run(["git", "-C", str(self.root), "-c", "user.name=Release Test",
                        "-c", "user.email=release@example.test", "commit", "-qm", "Unintegrated source"], check=True)
        candidate = CHECK.git(self.root, "rev-parse", "HEAD")
        with self.assertRaises(subprocess.CalledProcessError):
            CHECK.verify_source(self.root, candidate)

    def test_rejects_symlink_assets(self):
        checksum = self.archive.with_suffix(".zip.sha256")
        real = checksum.with_suffix(".real")
        checksum.rename(real)
        checksum.symlink_to(real.name)
        with self.assertRaisesRegex(ValueError, "regular files"):
            CHECK.verify_archive(self.root, TAG)


if __name__ == "__main__":
    unittest.main()
