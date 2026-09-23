"""Check the activated verifier's public contract without a live OAuth account."""

import contextlib
import importlib.util
import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_live_contract.py"
SPEC = importlib.util.spec_from_file_location("verify_live_contract", SCRIPT)
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)
ISSUER = "https://issuer.example/"


class Response(io.BytesIO):
    status = 200


def fake_urlopen(request, timeout=30):
    if request.full_url.endswith(verifier.REMOTE_METADATA):
        return Response(json.dumps({
            "resource": verifier.REMOTE_RESOURCE,
            "authorization_servers": [ISSUER],
            "scopes_supported": sorted(verifier.REMOTE_SCOPES),
        }).encode())
    if request.full_url == "https://fixture.test/":
        return Response(b'{"endpoint":"/mcp"}')
    raise AssertionError(f"Unexpected public request: {request.full_url}")


def fake_rpc(_base, method, params, *, challenge=True):
    if method == "tools/list":
        tools = []
        for name in sorted(verifier.EXPECTED_TOOLS | verifier.REMOTE_TOOLS):
            schemes = ([{"type": "oauth2", "scopes": sorted(verifier.REMOTE_SCOPES)}]
                       if name in verifier.REMOTE_TOOLS else [{"type": "noauth"}])
            tools.append({"name": name, "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
                          "annotations": {"title": name, "readOnlyHint": True},
                          "securitySchemes": schemes})
        return {"result": {"tools": tools}}
    name = params["name"]
    if name == "nymrel_remote_list_devices":
        metadata = {"mcp/www_authenticate": [
            f'Bearer resource_metadata="{verifier.REMOTE_METADATA}", scope="devices:read tools:read"'
        ]} if challenge else {}
        return {"result": {"isError": True, "_meta": metadata}}
    if name == "nymrel_golf_bag_gap":
        if "carry_distance_yards" in params["arguments"]["clubs"][0]:
            return {"result": {"content": [{"text": "average_gap_yards: 22"}]}}
        return {"result": {"isError": True, "content": [{"text": "carry_distance_yards required"}]}}
    raise AssertionError(f"Unexpected tool: {name}")


class ActivatedVerifierTests(unittest.TestCase):
    def run_verifier(self, *, challenge=True):
        output = io.StringIO()
        with (patch.object(sys, "argv", ["verify", "--remote-read", "--issuer", ISSUER, "https://fixture.test"]),
              patch.object(verifier.urllib.request, "urlopen", side_effect=fake_urlopen),
              patch.object(verifier, "rpc", side_effect=lambda *a, **k: fake_rpc(*a, **k, challenge=challenge)),
              contextlib.redirect_stdout(output)):
            result = verifier.main()
        return result, output.getvalue()

    def test_activated_catalog_metadata_and_challenge(self):
        result, output = self.run_verifier()
        self.assertEqual(result, 0, output)
        self.assertIn("private read requires caller OAuth", output)

    def test_missing_private_challenge_fails(self):
        result, output = self.run_verifier(challenge=False)
        self.assertEqual(result, 1, output)
        self.assertIn("FAIL private read requires caller OAuth", output)


if __name__ == "__main__":
    unittest.main()
