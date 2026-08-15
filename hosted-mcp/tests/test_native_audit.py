"""Regression guards for the local audit."""

import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

import native_audit  # noqa: E402


class ParsingPerformanceTests(unittest.TestCase):
    def test_meta_lookup_on_a_large_page_does_not_backtrack(self):
        """A big page with many non-matching meta tags used to hang for minutes.

        Unbounded `.*?` with DOTALL made each miss rescan the document.
        """
        filler = '<meta name="other" content="x">\n' * 6000
        html = f"<html><head>{filler}</head><body>{'y' * 400_000}</body></html>"

        start = time.monotonic()
        self.assertIsNone(native_audit._meta("description", html))
        self.assertIsNone(native_audit._meta("og:title", html))
        elapsed = time.monotonic() - start
        self.assertLess(elapsed, 2.0, f"meta lookup took {elapsed:.1f}s")


class SsrfGuardTests(unittest.TestCase):
    def test_private_and_metadata_hosts_are_refused(self):
        for target in (
            "http://127.0.0.1",
            "http://localhost:8080",
            "http://169.254.169.254/latest/meta-data/",
            "http://10.0.0.1",
        ):
            with self.assertRaises(native_audit.AuditInputError, msg=target):
                native_audit.audit_website(target)


class UnmeasuredScoringTests(unittest.TestCase):
    def test_unmeasured_checks_do_not_become_recommendations(self):
        """An unchecked item must never be reported as a problem we saw."""
        original = native_audit.BUDGET_SECONDS
        native_audit.BUDGET_SECONDS = 0.0001
        try:
            result = native_audit.audit_website("https://example.com")
        finally:
            native_audit.BUDGET_SECONDS = original

        self.assertTrue(result["unmeasured_checks"])
        self.assertLess(result["scored_out_of"], 100)
        for check in result["checks"]:
            if not check["measured"]:
                self.assertIsNone(check["passed"])


if __name__ == "__main__":
    unittest.main()
