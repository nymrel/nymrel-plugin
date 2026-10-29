import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).parents[2] / "scripts" / "registry-release.py"
SPEC = importlib.util.spec_from_file_location("registry_release", MODULE_PATH)
assert SPEC and SPEC.loader
registry_release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(registry_release)
SERVER_NAME = registry_release.SERVER_NAME
SERVER_SHA256 = registry_release.SERVER_SHA256
SERVER_URL = registry_release.SERVER_URL
SERVER_VERSION = registry_release.SERVER_VERSION
verify_listing = registry_release.verify_listing
verify_source = registry_release.verify_source
verify_target = registry_release.verify_target


class RegistryReleaseTests(unittest.TestCase):
    def target_env(self):
        sha = "a" * 40
        return {
            "GITHUB_REPOSITORY": "nymrel/nymrel-plugin",
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_SHA": sha,
            "EXPECTED_MAIN_SHA": sha,
        }

    def test_manual_target_accepts_only_exact_main_dispatch(self):
        verify_target(self.target_env())
        for key, value in (
            ("GITHUB_REPOSITORY", "other/repo"),
            ("GITHUB_REF", "refs/tags/v1.4.0"),
            ("GITHUB_EVENT_NAME", "push"),
            ("EXPECTED_MAIN_SHA", "b" * 40),
            ("GITHUB_SHA", "short"),
        ):
            with self.subTest(key=key, value=value):
                env = self.target_env()
                env[key] = value
                with self.assertRaises(ValueError):
                    verify_target(env)

    def test_source_requires_exact_pinned_bytes_and_metadata(self):
        # The checked-in source is the exact reviewed release artifact.
        source_path = Path(__file__).parents[2] / "server.json"
        self.assertEqual(verify_source(source_path)["name"], SERVER_NAME)
        good = {
            "name": SERVER_NAME,
            "version": SERVER_VERSION,
            "remotes": [{"url": SERVER_URL}],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "server.json"
            path.write_text(json.dumps(good), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                verify_source(path)
            # Isolate the semantic guard after matching a candidate's digest.
            wrong_name = {**good, "name": "io.github.other/server"}
            path.write_text(json.dumps(wrong_name), encoding="utf-8")
            candidate_digest = hashlib.sha256(path.read_bytes()).hexdigest()
            with patch.object(registry_release, "SERVER_SHA256", candidate_digest):
                with self.assertRaisesRegex(ValueError, "name or version"):
                    verify_source(path)

    def test_source_accepts_windows_checkout_line_endings_and_rejects_lone_cr(self):
        raw = (Path(__file__).parents[2] / "server.json").read_bytes().replace(b"\r\n", b"\n")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "server.json"
            path.write_bytes(raw.replace(b"\n", b"\r\n"))
            self.assertEqual(verify_source(path)["version"], SERVER_VERSION)
            path.write_bytes(raw + b"\r")
            with self.assertRaisesRegex(ValueError, "carriage returns"):
                verify_source(path)

    def test_registry_readback_requires_exact_listing_and_endpoint(self):
        record = {
            "name": SERVER_NAME,
            "version": SERVER_VERSION,
            "remotes": [{"url": SERVER_URL}],
        }
        self.assertEqual(verify_listing({"server": record}), (SERVER_NAME, SERVER_VERSION, SERVER_URL))
        for changed in (
            {**record, "name": "io.github.other/server"},
            {**record, "version": "1.4.1"},
            {**record, "remotes": [{"url": "https://example.test/mcp"}]},
            {"name": SERVER_NAME, "version": SERVER_VERSION, "remotes": []},
        ):
            with self.subTest(changed=changed):
                with self.assertRaises(ValueError):
                    verify_listing(changed)


if __name__ == "__main__":
    unittest.main()
