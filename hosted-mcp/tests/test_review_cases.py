"""The submission's review cases must describe the server that actually exists.

The v1.0 cases named a `render_website_audit` tool. No such tool has ever been
published on this connector, so three of the five positive cases could not pass
if a reviewer ran them - and a reviewer runs every tool. Nothing caught it
because the cases were prose in a JSON file that nothing read.

These tests read them against the server's own registry, so a case naming a tool
that does not exist fails here instead of in front of a reviewer.
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

import index  # noqa: E402


CASES_PATH = Path(__file__).resolve().parents[2] / "evals" / "review-cases.json"

MCP_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}

# OpenAI's submission requirements.
MIN_POSITIVE = 5
MIN_NEGATIVE = 3

# Words naming an outcome the suite does not observe. Allowed in a `must_not`
# clause (that is the point of the clause) and in prose that disclaims them.
FORECAST_WORDS = ("viral", "virality", "reach", "views", "retention")


def load_cases() -> dict:
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))


class ReviewCaseTests(unittest.IsolatedAsyncioTestCase):
    """Read the tool list the way a reviewer does - over the endpoint itself,
    not through FastMCP internals that move between versions."""

    async def asyncSetUp(self) -> None:
        self.cases = load_cases()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=index.app), base_url="http://mcp.test"
        ) as client:
            response = await client.post(
                "/mcp",
                headers=MCP_HEADERS,
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            )
        self.published = {t["name"] for t in response.json()["result"]["tools"]}

    async def test_every_expected_tool_actually_exists(self):
        """The defect that shipped in v1.0: a case naming a tool we never had."""
        for case in self.cases["positive"]:
            for name in case.get("tools_expected", []):
                with self.subTest(case=case["id"], tool=name):
                    self.assertIn(
                        name,
                        self.published,
                        f"{case['id']} expects '{name}', which this server does not publish. "
                        f"Published: {sorted(self.published)}",
                    )

    async def test_tools_under_test_matches_the_server(self):
        self.assertEqual(set(self.cases["tools_under_test"]), self.published)

    async def test_every_published_tool_has_a_positive_case(self):
        """A reviewer runs every tool, so every tool needs a case."""
        covered = {n for c in self.cases["positive"] for n in c.get("tools_expected", [])}
        self.assertEqual(
            covered,
            self.published,
            f"tools with no positive case: {sorted(self.published - covered)}",
        )

    async def test_meets_submission_minimums(self):
        self.assertGreaterEqual(len(self.cases["positive"]), MIN_POSITIVE)
        self.assertGreaterEqual(len(self.cases["negative"]), MIN_NEGATIVE)

    async def test_every_case_is_complete(self):
        for group in ("positive", "negative"):
            for case in self.cases[group]:
                with self.subTest(case=case.get("id")):
                    self.assertTrue(case.get("id"))
                    self.assertTrue(case.get("prompt"))
                    self.assertTrue(case.get("expected"))
                    # Every claim about behaviour must say where it was observed.
                    self.assertTrue(
                        case.get("grounded_in"),
                        "an expectation with no observed basis is a guess",
                    )

    async def test_no_positive_case_expects_a_forecast(self):
        """Nymrel reports what it measured; a case must not ask for a prediction."""
        for case in self.cases["positive"]:
            joined = " ".join(case.get("expected", [])).lower()
            for word in FORECAST_WORDS:
                with self.subTest(case=case["id"], word=word):
                    self.assertNotRegex(
                        joined,
                        rf"(predict|estimate|forecast)[^.]*{re.escape(word)}",
                        "a positive case must never expect the assistant to forecast an outcome",
                    )


if __name__ == "__main__":
    unittest.main()
