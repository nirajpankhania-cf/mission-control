"""The real client, exercised against a monkeypatched urlopen. No network."""
import io
import json
import os
import unittest
import urllib.error
from unittest import mock

from mission_control.anthropic_client import API_URL, API_VERSION, FALLBACK_BETA, AnthropicClient
from mission_control.fake_model import FakeModelClient
from mission_control.model_interface import ModelClient, ModelError, ModelRequest
from mission_control.prompts import SORT_SCHEMA, build_draft_request, build_sort_request
from mission_control.server import choose_client

REPORT = {
    "name": "Ada", "station": "Propulsion", "wind_knots": 12.0, "temp_c": 18.0, "fuel_pct": 99.0,
    "note": "Valve 3 opened 200 ms late on the second cycle.",
}


class FakeResponse(object):
    def __init__(self, payload):
        self.body = json.dumps(payload).encode("utf-8") if not isinstance(payload, bytes) else payload

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def api_reply(data, stop_reason="end_turn", model="claude-haiku-5-5", input_tokens=321, output_tokens=45,
              with_thinking=True):
    content = []
    if with_thinking:
        content.append({"type": "thinking", "thinking": "", "signature": "x"})
    content.append({"type": "text", "text": json.dumps(data)})
    return {
        "id": "msg_1", "type": "message", "role": "assistant", "model": model, "content": content,
        "stop_reason": stop_reason, "stop_details": {"type": "refusal", "category": "cyber"} if stop_reason == "refusal" else None,
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
    }


def http_error(code, body=b'{"type":"error","error":{"type":"overloaded_error","message":"busy"}}'):
    return urllib.error.HTTPError(API_URL, code, "error", {}, io.BytesIO(body))


class Recorder(object):
    """Stands in for urlopen: records requests and plays scripted outcomes."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.requests = []

    def __call__(self, request, timeout=None):
        self.requests.append((request, timeout))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return FakeResponse(outcome)


def make_client(outcomes, **kwargs):
    recorder = Recorder(outcomes)
    client = AnthropicClient("sk-test", sleep=lambda seconds: None, urlopen=recorder, **kwargs)
    return client, recorder


class TestRequestShape(unittest.TestCase):
    def test_body_carries_model_schema_prompt_and_effort(self):
        client, recorder = make_client([api_reply({"subsystem": "propulsion", "severity": "low", "reason": "x"})])
        request = build_sort_request("claude-haiku-5-5", REPORT)
        client.complete(request)
        http_request, timeout = recorder.requests[0]
        self.assertEqual(http_request.full_url, API_URL)
        self.assertEqual(http_request.get_method(), "POST")
        self.assertEqual(timeout, 60)
        body = json.loads(http_request.data.decode("utf-8"))
        self.assertEqual(body["model"], "claude-haiku-5-5")
        self.assertEqual(body["output_config"]["format"], {"type": "json_schema", "schema": SORT_SCHEMA})
        self.assertEqual(body["output_config"]["effort"], "low")
        self.assertEqual(body["system"], request.system)
        self.assertEqual(body["messages"], [{"role": "user", "content": request.prompt}])
        self.assertEqual(body["max_tokens"], request.max_tokens)
        self.assertNotIn("fallbacks", body)
        self.assertNotIn("context", body)
        self.assertNotIn("temperature", body)

    def test_headers_carry_key_and_version(self):
        client, recorder = make_client([api_reply({"subsystem": "propulsion", "severity": "low", "reason": "x"})])
        client.complete(build_sort_request("claude-haiku-5-5", REPORT))
        headers = {k.lower(): v for k, v in recorder.requests[0][0].header_items()}
        self.assertEqual(headers["x-api-key"], "sk-test")
        self.assertEqual(headers["anthropic-version"], API_VERSION)
        self.assertEqual(headers["content-type"], "application/json")
        self.assertNotIn("anthropic-beta", headers)

    def test_strong_model_opts_into_server_side_fallbacks(self):
        client, recorder = make_client([api_reply({"summary": "s", "recommended_action": "a"}, model="claude-opus-5-5")])
        context = dict(REPORT, verdict="go", violations=[], subsystem="propulsion", severity="low",
                       effective_severity="low", brief_by_minutes=30, checks={}, review_reasons=[])
        client.complete(build_draft_request("claude-opus-5-5", context, 1))
        http_request = recorder.requests[0][0]
        body = json.loads(http_request.data.decode("utf-8"))
        self.assertEqual(body["fallbacks"], "default")
        self.assertEqual(body["output_config"]["effort"], "medium")
        headers = {k.lower(): v for k, v in http_request.header_items()}
        self.assertEqual(headers["anthropic-beta"], FALLBACK_BETA)


class TestReplyParsing(unittest.TestCase):
    def request(self):
        return build_sort_request("claude-haiku-5-5", REPORT)

    def test_usage_and_data_are_parsed_from_the_text_block(self):
        client, _ = make_client([api_reply({"subsystem": "avionics", "severity": "medium", "reason": "r"},
                                           input_tokens=1234, output_tokens=56)])
        reply = client.complete(self.request())
        self.assertEqual(reply.data, {"subsystem": "avionics", "severity": "medium", "reason": "r"})
        self.assertEqual((reply.input_tokens, reply.output_tokens), (1234, 56))
        self.assertEqual(reply.model, "claude-haiku-5-5")
        self.assertEqual(reply.stop_reason, "end_turn")

    def test_refusal_is_a_model_error(self):
        client, _ = make_client([api_reply({}, stop_reason="refusal")])
        with self.assertRaises(ModelError) as raised:
            client.complete(self.request())
        self.assertIn("refused", str(raised.exception))

    def test_max_tokens_is_a_model_error(self):
        client, _ = make_client([api_reply({"subsystem": "avionics"}, stop_reason="max_tokens")])
        with self.assertRaises(ModelError):
            client.complete(self.request())

    def test_non_json_text_is_a_model_error(self):
        payload = api_reply({})
        payload["content"][-1]["text"] = "propulsion, low"
        client, _ = make_client([payload])
        with self.assertRaises(ModelError):
            client.complete(self.request())

    def test_missing_text_block_is_a_model_error(self):
        payload = api_reply({})
        payload["content"] = [{"type": "thinking", "thinking": ""}]
        client, _ = make_client([payload])
        with self.assertRaises(ModelError):
            client.complete(self.request())

    def test_error_object_is_a_model_error(self):
        client, _ = make_client([{"type": "error", "error": {"type": "invalid_request_error", "message": "bad"}}])
        with self.assertRaises(ModelError):
            client.complete(self.request())


class TestRetries(unittest.TestCase):
    def request(self):
        return build_sort_request("claude-haiku-5-5", REPORT)

    def test_500_is_retried_once_then_succeeds(self):
        client, recorder = make_client([http_error(500), api_reply({"subsystem": "weather", "severity": "low", "reason": ""})])
        reply = client.complete(self.request())
        self.assertEqual(reply.data["subsystem"], "weather")
        self.assertEqual(len(recorder.requests), 2)

    def test_429_then_500_gives_up_after_one_retry(self):
        client, recorder = make_client([http_error(429), http_error(503)])
        with self.assertRaises(ModelError) as raised:
            client.complete(self.request())
        self.assertEqual(len(recorder.requests), 2)
        self.assertIn("503", str(raised.exception))

    def test_400_is_not_retried(self):
        client, recorder = make_client([http_error(400, b'{"error":{"message":"bad schema"}}')])
        with self.assertRaises(ModelError) as raised:
            client.complete(self.request())
        self.assertEqual(len(recorder.requests), 1)
        self.assertIn("bad schema", str(raised.exception))

    def test_network_error_is_retried_once(self):
        client, recorder = make_client([urllib.error.URLError("dns down"), urllib.error.URLError("dns down")])
        with self.assertRaises(ModelError):
            client.complete(self.request())
        self.assertEqual(len(recorder.requests), 2)


class TestClientChoice(unittest.TestCase):
    def test_is_a_model_client_and_needs_a_key(self):
        self.assertIsInstance(AnthropicClient("sk-test", urlopen=lambda *a, **k: None), ModelClient)
        with self.assertRaises(ValueError):
            AnthropicClient("")

    def test_no_key_means_the_fake(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            self.assertIsInstance(choose_client(), FakeModelClient)

    def test_key_means_the_real_client_without_touching_the_network(self):
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}):
            with mock.patch("urllib.request.urlopen", side_effect=AssertionError("network touched")):
                client = choose_client()
        self.assertEqual(client.name, "anthropic")


if __name__ == "__main__":
    unittest.main()
