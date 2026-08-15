"""Isolated contract tests for the Nymrel public FastMCP HTTP facade."""

from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

import requests

import nymrel_public_mcp_server as server


class FakeResponse:
    def __init__(self, status_code: int, payload: object, content_type: str = "application/json"):
        self.status_code = status_code
        self.payload = payload
        self.headers = {"content-type": content_type}

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def _html_404() -> FakeResponse:
    """The exact upstream shape while /api/v1/tools/* is not deployed."""
    return FakeResponse(404, ValueError("Expecting value"), content_type="text/html; charset=utf-8")


class ClientTests(unittest.TestCase):
    def test_forwards_exact_operation_payload_and_bearer(self):
        calls = []

        def requester(method, url, **kwargs):
            calls.append((method, url, kwargs))
            return FakeResponse(200, {"suggestions": []})

        client = server.NymrelPublicApiClient(
            base_url="https://api.example.test/api/v1/tools",
            bearer_token="token-value",
            requester=requester,
        )
        result = client.call("find-domain", {"keyword_or_concept": "calm studio"})

        self.assertEqual(result, {"suggestions": []})
        method, url, kwargs = calls[0]
        self.assertEqual(method, "POST")
        self.assertEqual(url, "https://api.example.test/api/v1/tools/find-domain")
        self.assertEqual(kwargs["json"], {"keyword_or_concept": "calm studio"})
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer token-value")
        self.assertEqual(kwargs["timeout"], server.DEFAULT_TIMEOUT_SECONDS)

    def test_intake_fails_before_network_when_auth_is_missing(self):
        calls = []
        client = server.NymrelPublicApiClient(
            base_url="https://api.example.test/api/v1/tools",
            bearer_token="",
            requester=lambda *args, **kwargs: calls.append((args, kwargs)),
        )
        with self.assertRaises(server.NymrelPublicApiError) as caught:
            client.call("submit-studio-brief", {"title": "Brief"}, require_auth=True)
        self.assertEqual(caught.exception.code, "INTAKE_AUTH_NOT_CONFIGURED")
        self.assertEqual(calls, [])

    def test_network_failure_is_safe_and_retryable(self):
        def requester(*_args, **_kwargs):
            raise requests.ConnectionError("private host and token must not escape")

        client = server.NymrelPublicApiClient(
            base_url="https://api.example.test/api/v1/tools",
            requester=requester,
        )
        with self.assertRaises(server.NymrelPublicApiError) as caught:
            client.call("audit-website", {"url": "https://example.com"})
        self.assertEqual(caught.exception.code, "UPSTREAM_UNAVAILABLE")
        self.assertTrue(caught.exception.retryable)
        self.assertNotIn("private", caught.exception.message)
        self.assertNotIn("token", caught.exception.message)

    def test_upstream_error_keeps_only_safe_code(self):
        client = server.NymrelPublicApiClient(
            base_url="https://api.example.test/api/v1/tools",
            requester=lambda *_args, **_kwargs: FakeResponse(
                503,
                {"error": {"code": "PROVIDER_UNAVAILABLE", "message": "sk_live_never_echo"}},
            ),
        )
        with self.assertRaises(server.NymrelPublicApiError) as caught:
            client.call("find-domain", {"keyword_or_concept": "studio"})
        self.assertEqual(caught.exception.code, "PROVIDER_UNAVAILABLE")
        self.assertEqual(caught.exception.message, server.MESSAGE_SERVER_ERROR)
        self.assertNotIn("sk_live", caught.exception.message)

    def test_rejects_non_https_nonlocal_base_url(self):
        with self.assertRaises(server.NymrelPublicApiError) as caught:
            server.NymrelPublicApiClient(base_url="http://api.example.test/tools")
        self.assertEqual(caught.exception.code, "INVALID_API_BASE_URL")

    def test_rejects_invalid_timeout_configuration(self):
        for timeout in ("not-a-number", 0, -1, float("inf"), 121):
            with self.subTest(timeout=timeout), self.assertRaises(server.NymrelPublicApiError) as caught:
                server.NymrelPublicApiClient(
                    base_url="https://api.example.test/tools",
                    timeout_seconds=timeout,
                )
            self.assertEqual(caught.exception.code, "INVALID_API_TIMEOUT")


class ErrorTaxonomyTests(unittest.TestCase):
    """Each upstream condition must produce its own code, sentence and retryable."""

    def _fail(self, responder, operation="audit-website", payload=None):
        client = server.NymrelPublicApiClient(
            base_url="https://api.example.test/api/v1/tools",
            requester=responder if callable(responder) else (lambda *a, **k: responder),
        )
        with self.assertRaises(server.NymrelPublicApiError) as caught:
            client.call(operation, payload or {"url": "https://example.com"})
        return caught.exception

    # -- the rolling-out state -------------------------------------------------

    def test_html_404_from_undeployed_route_is_not_deployed_and_not_retryable(self):
        error = self._fail(_html_404())
        self.assertEqual(error.code, "UPSTREAM_NOT_DEPLOYED")
        self.assertEqual(error.message, server.MESSAGE_NOT_DEPLOYED)
        self.assertFalse(error.retryable)
        self.assertIn("rolling out", error.message)

    def test_405_is_also_read_as_not_deployed(self):
        self.assertEqual(self._fail(FakeResponse(405, {})).code, "UPSTREAM_NOT_DEPLOYED")

    def test_200_html_app_shell_is_read_as_not_deployed(self):
        response = FakeResponse(200, ValueError("no json"), content_type="text/html")
        self.assertEqual(self._fail(response).code, "UPSTREAM_NOT_DEPLOYED")

    def test_deployed_route_reporting_its_own_404_keeps_that_code(self):
        """A real API 404 is about the thing asked for, not a missing route."""
        response = FakeResponse(404, {"error": {"code": "JURISDICTION_NOT_FOUND"}})
        error = self._fail(response, "local-permit-lookup", {"city_or_zip": "Nowhere", "trade_type": "electrical"})
        self.assertEqual(error.code, "JURISDICTION_NOT_FOUND")

    # -- transport failures ----------------------------------------------------

    def test_timeout_is_its_own_code_and_is_retryable(self):
        def responder(*_args, **_kwargs):
            raise requests.Timeout("read timed out")

        error = self._fail(responder)
        self.assertEqual(error.code, "UPSTREAM_TIMEOUT")
        self.assertTrue(error.retryable)

    def test_connection_failure_is_unavailable_and_retryable(self):
        def responder(*_args, **_kwargs):
            raise requests.ConnectionError("private-host:5432")

        error = self._fail(responder)
        self.assertEqual(error.code, "UPSTREAM_UNAVAILABLE")
        self.assertTrue(error.retryable)
        self.assertNotIn("private-host", error.message)

    # -- server-side failures --------------------------------------------------

    def test_bare_500_is_upstream_5xx_and_not_retryable(self):
        error = self._fail(FakeResponse(500, {}))
        self.assertEqual(error.code, "UPSTREAM_5XX")
        self.assertEqual(error.message, server.MESSAGE_SERVER_ERROR)
        self.assertFalse(error.retryable, "a 500 is not known to clear on retry")

    def test_gateway_5xx_are_retryable(self):
        for status in (502, 503, 504):
            with self.subTest(status=status):
                error = self._fail(FakeResponse(status, {}))
                self.assertEqual(error.code, "UPSTREAM_5XX")
                self.assertTrue(error.retryable)

    def test_rate_limit_is_retryable(self):
        error = self._fail(FakeResponse(429, {}))
        self.assertEqual(error.code, "UPSTREAM_RATE_LIMITED")
        self.assertTrue(error.retryable)

    # -- malformed answers -----------------------------------------------------

    def test_unparseable_json_body_is_malformed_and_not_retryable(self):
        response = FakeResponse(200, ValueError("Expecting value"))
        error = self._fail(response)
        self.assertEqual(error.code, "UPSTREAM_MALFORMED")
        self.assertFalse(error.retryable, "a malformed body repeats on retry")

    def test_json_that_is_not_an_object_is_malformed(self):
        self.assertEqual(self._fail(FakeResponse(200, [1, 2, 3])).code, "UPSTREAM_MALFORMED")

    # -- caller mistakes -------------------------------------------------------

    def test_upstream_400_without_a_code_is_invalid_input(self):
        error = self._fail(FakeResponse(400, {}))
        self.assertEqual(error.code, "INVALID_INPUT")
        self.assertFalse(error.retryable)

    def test_upstream_400_with_a_code_keeps_the_specific_code(self):
        response = FakeResponse(400, {"error": {"code": "URL_UNREACHABLE"}})
        self.assertEqual(self._fail(response).code, "URL_UNREACHABLE")

    def test_other_4xx_is_rejected_and_not_retryable(self):
        error = self._fail(FakeResponse(403, {}))
        self.assertEqual(error.code, "UPSTREAM_REJECTED")
        self.assertFalse(error.retryable)

    def test_blank_required_value_fails_before_the_network(self):
        calls = []

        def responder(*args, **kwargs):
            calls.append((args, kwargs))
            return FakeResponse(200, {})

        client = server.NymrelPublicApiClient(
            base_url="https://api.example.test/api/v1/tools", requester=responder
        )
        with self.assertRaises(server.NymrelPublicApiError) as caught:
            client.call("audit-website", {"url": "   "})
        self.assertEqual(caught.exception.code, "INVALID_INPUT")
        self.assertIn("url", caught.exception.message)
        self.assertEqual(calls, [], "a caller mistake must not reach the API")

    def test_non_web_address_is_invalid_input(self):
        client = server.NymrelPublicApiClient(
            base_url="https://api.example.test/api/v1/tools",
            requester=lambda *a, **k: FakeResponse(200, {}),
        )
        with self.assertRaises(server.NymrelPublicApiError) as caught:
            client.call("audit-website", {"url": "example.com"})
        self.assertEqual(caught.exception.code, "INVALID_INPUT")

    def test_empty_list_argument_is_invalid_input(self):
        client = server.NymrelPublicApiClient(
            base_url="https://api.example.test/api/v1/tools",
            requester=lambda *a, **k: FakeResponse(200, {}),
        )
        with self.assertRaises(server.NymrelPublicApiError) as caught:
            client.call(
                "evaluate-fantasy-trade",
                {"side_a_players": [], "side_b_players": ["B"], "league_format": "dynasty"},
            )
        self.assertEqual(caught.exception.code, "INVALID_INPUT")
        self.assertIn("side_a_players", caught.exception.message)

    def test_valid_payload_still_reaches_the_api(self):
        """The input rules must not block a well-formed call."""
        client = server.NymrelPublicApiClient(
            base_url="https://api.example.test/api/v1/tools",
            requester=lambda *a, **k: FakeResponse(200, {"ok": True}),
        )
        self.assertEqual(
            client.call("golf-bag-gap", {"clubs": [{"name": "7i", "carry_yards": 150}]}),
            {"ok": True},
        )

    # -- every error is readable ----------------------------------------------

    def test_every_error_carries_one_plain_sentence(self):
        cases = [
            FakeResponse(400, {}),
            FakeResponse(403, {}),
            _html_404(),
            FakeResponse(405, {}),
            FakeResponse(429, {}),
            FakeResponse(500, {}),
            FakeResponse(503, {}),
            FakeResponse(200, [1]),
        ]
        for response in cases:
            with self.subTest(status=response.status_code):
                message = self._fail(response).message
                self.assertTrue(message.endswith("."), message)
                self.assertGreater(len(message.split()), 6, "not a full sentence")
                self.assertNotIn("{", message)
                self.assertNotIn("None", message)


class ToolFacadeTests(unittest.TestCase):
    def test_tool_returns_the_api_object_not_a_json_string(self):
        client = unittest.mock.Mock()
        client.call.return_value = {"score": 88, "grade": "A"}
        with patch.object(server, "_client", return_value=client):
            payload = server._call_tool("audit-website", {"url": "https://example.com"})
        self.assertIsInstance(payload, dict, "returning a string is what double-encodes the result")
        self.assertEqual(payload, {"score": 88, "grade": "A"})
        client.call.assert_called_once_with(
            "audit-website",
            {"url": "https://example.com"},
            require_auth=False,
        )

    def test_tool_failure_is_structured_without_fake_success(self):
        client = unittest.mock.Mock()
        client.call.side_effect = server.NymrelPublicApiError(
            "UPSTREAM_NOT_DEPLOYED",
            server.MESSAGE_NOT_DEPLOYED,
            retryable=False,
        )
        with patch.object(server, "_client", return_value=client):
            payload = server._call_tool("find-domain", {"keyword_or_concept": "studio"})
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], "UPSTREAM_NOT_DEPLOYED")
        self.assertEqual(payload["error"]["message"], server.MESSAGE_NOT_DEPLOYED)
        self.assertFalse(payload["error"]["retryable"])
        self.assertNotIn("suggestions", payload)

    def test_all_seven_operations_are_registered(self):
        self.assertEqual(len(server.OPERATIONS), 7)
        self.assertEqual(
            server.OPERATIONS,
            {
                "audit-website",
                "find-domain",
                "evaluate-fantasy-trade",
                "golf-bag-gap",
                "local-permit-lookup",
                "social-clip-score",
                "submit-studio-brief",
            },
        )


class ServerEntrypointTests(unittest.TestCase):
    def test_defaults_to_stdio(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(server.mcp, "run") as run:
            server.run_server()
        run.assert_called_once_with(transport="stdio")

    def test_cloud_http_mode_is_stateless_and_path_bound(self):
        with patch.dict(os.environ, {
            "NYMREL_MCP_TRANSPORT": "http",
            "NYMREL_MCP_HOST": "0.0.0.0",
            "NYMREL_MCP_PORT": "8080",
            "NYMREL_MCP_PATH": "/mcp",
        }, clear=True), patch.object(server.mcp, "run") as run:
            server.run_server()
        run.assert_called_once_with(
            transport="http",
            host="0.0.0.0",
            port=8080,
            path="/mcp",
            stateless_http=True,
            json_response=True,
        )

    def test_rejects_unsafe_cloud_configuration(self):
        cases = [
            {"NYMREL_MCP_TRANSPORT": "sse"},
            {"NYMREL_MCP_TRANSPORT": "http", "NYMREL_MCP_PORT": "0"},
            {"NYMREL_MCP_TRANSPORT": "http", "NYMREL_MCP_PATH": "//other-host"},
        ]
        for environment in cases:
            with self.subTest(environment=environment), patch.dict(os.environ, environment, clear=True):
                with self.assertRaises(server.NymrelPublicApiError):
                    server.run_server()


if __name__ == "__main__":
    unittest.main(verbosity=2)
