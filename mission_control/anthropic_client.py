"""The real model client: Anthropic Messages API over HTTPS with urllib.

No SDK, so a grader needs nothing installed. Every call sends a JSON schema
through ``output_config.format`` and the reply text is parsed as JSON; the
caller still validates the parsed value in code. A 429, a 5xx or a network
error is retried once. A refusal or a truncated reply is a ModelError.
"""
import json
import socket
import time
import urllib.error
import urllib.request

from mission_control.model_interface import ModelClient, ModelError, ModelReply

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2026-10-21"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
RETRY_STATUSES = (429, 500, 502, 503, 504, 529)


def supports_fallbacks(model):
    """Server-side refusal fallbacks exist for the Opus, Sonnet and Fable lines, not Haiku."""
    return not model.startswith("claude-haiku")


class AnthropicClient(ModelClient):
    name = "anthropic"

    def __init__(self, api_key, timeout=60, retries=1, sleep=time.sleep, urlopen=None):
        if not api_key:
            raise ValueError("an API key is required for the real client")
        self.api_key = api_key
        self.timeout = timeout
        self.retries = retries
        self.sleep = sleep
        self.urlopen = urlopen or urllib.request.urlopen

    # ----- request -------------------------------------------------------
    def build_body(self, request):
        body = {
            "model": request.model,
            "max_tokens": request.max_tokens,
            "system": request.system,
            "messages": [{"role": "user", "content": request.prompt}],
            "output_config": {
                "format": {"type": "json_schema", "schema": request.schema},
                "effort": request.effort,
            },
        }
        if supports_fallbacks(request.model):
            body["fallbacks"] = "default"
        return body

    def build_headers(self, request):
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
            "accept": "application/json",
        }
        if supports_fallbacks(request.model):
            headers["anthropic-beta"] = FALLBACK_BETA
        return headers

    # ----- call ----------------------------------------------------------
    def complete(self, request):
        data = json.dumps(self.build_body(request)).encode("utf-8")
        headers = self.build_headers(request)
        last_error = None
        for attempt in range(self.retries + 1):
            http_request = urllib.request.Request(API_URL, data=data, headers=headers, method="POST")
            try:
                with self.urlopen(http_request, timeout=self.timeout) as response:
                    raw = response.read()
                return self.parse_reply(raw, request)
            except urllib.error.HTTPError as error:
                detail = _read_error(error)
                last_error = ModelError("HTTP %s from the Anthropic API: %s" % (error.code, detail))
                if error.code not in RETRY_STATUSES:
                    raise last_error
            except (urllib.error.URLError, socket.timeout, ConnectionError, OSError) as error:
                last_error = ModelError("network error calling the Anthropic API: %s" % error)
            if attempt < self.retries:
                self.sleep(1.0 * (attempt + 1))
        raise last_error

    # ----- reply ---------------------------------------------------------
    def parse_reply(self, raw, request):
        try:
            payload = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
        except (ValueError, UnicodeDecodeError) as error:
            raise ModelError("the API reply was not JSON: %s" % error)
        if not isinstance(payload, dict):
            raise ModelError("the API reply was not an object")
        if payload.get("type") == "error":
            raise ModelError("API error: %s" % json.dumps(payload.get("error")))
        stop_reason = payload.get("stop_reason")
        if stop_reason == "refusal":
            details = payload.get("stop_details") or {}
            raise ModelError("the model refused the request (category %s)" % details.get("category"))
        if stop_reason == "max_tokens":
            raise ModelError("the reply was cut off at max_tokens")
        text = None
        for block in payload.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text")
                break
        if not isinstance(text, str):
            raise ModelError("the reply had no text block")
        try:
            parsed = json.loads(text)
        except ValueError as error:
            raise ModelError("the reply text was not JSON: %s" % error)
        usage = payload.get("usage") or {}
        return ModelReply(
            data=parsed,
            text=text,
            input_tokens=int(usage.get("input_tokens") or 0),
            output_tokens=int(usage.get("output_tokens") or 0),
            model=payload.get("model") or request.model,
            stop_reason=stop_reason or "end_turn",
        )


def _read_error(error):
    try:
        body = error.read().decode("utf-8", "replace")
    except Exception:  # pragma: no cover - the body is only for the message
        return ""
    return body[:500]
