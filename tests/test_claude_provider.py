"""Claude as the first-choice provider (claude_provider.py).

Runs the real `anthropic` SDK against an in-process mock transport, so the
request the SDK actually puts on the wire is what gets asserted — no network,
no key, no spend.
"""

import json
import os
import sys
from types import SimpleNamespace

import anthropic
import httpx2
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import analytics_agent as aa  # noqa: E402
import claude_provider as cp  # noqa: E402

HEADERS = {"request-id": "req_test", "anthropic-workspace-id": "wrkspc_test"}


def _message(text="SELECT 1", stop_reason="end_turn", model="claude-sonnet-5-5"):
    content = [{"type": "thinking", "thinking": "", "signature": "sig"}]
    if text is not None:
        content.append({"type": "text", "text": text})
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": 10,
            "output_tokens": 5,
            "cache_read_input_tokens": 100,
            "cache_creation_input_tokens": 0,
        },
    }


def _sse(texts, stop_reason="end_turn"):
    events = [
        ("message_start", {"type": "message_start", "message": {**_message(None), "content": [], "stop_reason": None}}),
        (
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "thinking", "thinking": "", "signature": ""},
            },
        ),
        (
            "content_block_delta",
            {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": ""}},
        ),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        (
            "content_block_start",
            {"type": "content_block_start", "index": 1, "content_block": {"type": "text", "text": ""}},
        ),
    ]
    for t in texts:
        events.append(
            (
                "content_block_delta",
                {"type": "content_block_delta", "index": 1, "delta": {"type": "text_delta", "text": t}},
            )
        )
    events += [
        ("content_block_stop", {"type": "content_block_stop", "index": 1}),
        (
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                "usage": {"output_tokens": 5},
            },
        ),
        ("message_stop", {"type": "message_stop"}),
    ]
    return "".join(f"event: {e}\ndata: {json.dumps(d)}\n\n" for e, d in events).encode()


class Server:
    """Answers each POST /v1/messages from a per-model script; records requests."""

    def __init__(self, by_model):
        self.by_model, self.requests = by_model, []

    def __call__(self, request):
        body = json.loads(request.content)
        self.requests.append(body)
        status, payload = self.by_model[body["model"]]
        if status != 200:
            return httpx2.Response(status, json={"type": "error", "error": payload}, headers=HEADERS)
        if body.get("stream"):
            return httpx2.Response(200, content=payload, headers={**HEADERS, "content-type": "text/event-stream"})
        return httpx2.Response(200, json=payload, headers=HEADERS)


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setattr(cp, "_client", None)
    monkeypatch.setattr(cp, "_unusable_until", None)
    monkeypatch.setattr(cp, "_dead_models", {})
    aa._mark_primary_unusable(False)
    yield


def _install(monkeypatch, by_model):
    server = Server(by_model)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    sdk = anthropic.Anthropic(
        api_key="sk-ant-test",
        max_retries=0,
        http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(server)),
    )
    monkeypatch.setattr(cp, "_client", cp.ClaudeClient(sdk))
    return server


def _sql_call(c, m):
    return lambda: c.with_raw_response.chat.completions.create(
        model=m,
        temperature=0.1,
        max_tokens=2048,
        messages=[
            {"role": "system", "content": "SCHEMA"},
            {"role": "assistant", "content": "orphan history turn"},
            {"role": "user", "content": "q"},
        ],
    )


def test_off_without_a_key():
    assert cp.get_client() is None
    assert cp.call_first(_sql_call) is None
    assert aa.get_preferred_tier() == aa.get_primary_tier()


def test_request_translation_and_openai_shaped_reply(monkeypatch):
    server = _install(monkeypatch, {"claude-sonnet-5-5": (200, _message("SELECT 42"))})
    raw, model = cp.call_first(_sql_call)
    assert model == "claude-sonnet-5-5"
    resp = raw.parse()
    assert resp.choices[0].message.content == "SELECT 42"
    assert resp.usage.prompt_tokens == 110 and resp.usage.completion_tokens == 5
    assert raw.headers.get("anthropic-workspace-id") == "wrkspc_test"
    sent = server.requests[0]
    assert "temperature" not in sent  # 400s on current models
    assert sent["max_tokens"] >= cp.MIN_MAX_TOKENS  # room for adaptive thinking
    assert sent["output_config"] == {"effort": "low"}
    assert sent["system"] == [{"type": "text", "text": "SCHEMA", "cache_control": {"type": "ephemeral"}}]
    assert sent["messages"] == [{"role": "user", "content": "q"}]  # user turn first


def test_overloaded_model_moves_down_the_ranking(monkeypatch):
    _install(
        monkeypatch,
        {
            "claude-sonnet-5-5": (529, {"type": "overloaded_error", "message": "busy"}),
            "claude-haiku-5-5": (200, _message("SELECT 2", model="claude-haiku-5-5")),
        },
    )
    raw, model = cp.call_first(_sql_call)
    assert model == "claude-haiku-5-5" and raw.parse().choices[0].message.content == "SELECT 2"
    assert not cp.is_latched()


def test_retired_model_is_skipped_until_recheck(monkeypatch):
    server = _install(
        monkeypatch,
        {
            "claude-sonnet-5-5": (404, {"type": "not_found_error", "message": "model"}),
            "claude-haiku-5-5": (200, _message(model="claude-haiku-5-5")),
        },
    )
    assert cp.call_first(_sql_call)[1] == "claude-haiku-5-5"
    assert cp.call_first(_sql_call)[1] == "claude-haiku-5-5"
    assert [r["model"] for r in server.requests] == ["claude-sonnet-5-5", "claude-haiku-5-5", "claude-haiku-5-5"]


@pytest.mark.parametrize(
    "status,error",
    [
        (401, {"type": "authentication_error", "message": "invalid x-api-key"}),
        (
            400,
            {
                "type": "invalid_request_error",
                "message": "This API key is not scoped to a workspace, so this request must include the anthropic-workspace-id header",
            },
        ),
        (
            400,
            {"type": "invalid_request_error", "message": "Your credit balance is too low to access the Anthropic API."},
        ),
    ],
)
def test_dead_key_or_empty_balance_latches_claude_out(monkeypatch, status, error):
    server = _install(monkeypatch, {"claude-sonnet-5-5": (status, error), "claude-haiku-5-5": (200, _message())})
    assert cp.call_first(_sql_call) is None
    assert cp.is_latched()
    assert cp.call_first(_sql_call) is None
    assert len(server.requests) == 1  # no second doomed round trip
    assert aa.get_preferred_tier() == aa.get_primary_tier()


@pytest.mark.parametrize("message", [_message(None), _message("x", stop_reason="refusal")])
def test_refusal_or_empty_answer_falls_through(monkeypatch, message):
    _install(monkeypatch, {"claude-sonnet-5-5": (200, message)})
    assert cp.call_first(_sql_call) is None
    assert not cp.is_latched()


def test_stream_yields_text_and_keepalive_chunks(monkeypatch):
    _install(monkeypatch, {"claude-sonnet-5-5": (200, _sse(["Hello", " world"]))})
    stream, _ = cp.call_first(
        lambda c, m: (
            lambda: c.chat.completions.create(model=m, messages=[{"role": "user", "content": "q"}], stream=True)
        )
    )
    chunks = [ch.choices[0].delta.content for ch in stream]
    assert "".join(chunks) == "Hello world"
    assert "" in chunks  # thinking/bookkeeping events keep the stall guard fed


def test_stream_refusal_raises_for_the_caller(monkeypatch):
    _install(monkeypatch, {"claude-sonnet-5-5": (200, _sse([], stop_reason="refusal"))})
    stream, _ = cp.call_first(
        lambda c, m: (
            lambda: c.chat.completions.create(model=m, messages=[{"role": "user", "content": "q"}], stream=True)
        )
    )
    with pytest.raises(cp.ClaudeRefusal):
        list(stream)
    assert cp.is_claude_error(cp.ClaudeRefusal("x"))


class _FakeOpenAI:
    """Primary OpenAI-compatible client: records that it was called."""

    def __init__(self):
        self.calls = 0
        completions = SimpleNamespace(create=self._create)
        self.with_raw_response = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    def _create(self, **_):
        self.calls += 1
        msg = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="SELECT 'openrouter'"))], usage=None
        )
        return SimpleNamespace(parse=lambda: msg, headers={})


def test_generate_sql_prefers_claude_and_records_the_tier(monkeypatch):
    _install(monkeypatch, {"claude-sonnet-5-5": (200, _message("SELECT 'claude'"))})
    primary = _FakeOpenAI()
    aa.begin_request_tier_tracking()
    sql, usage, _ = aa.generate_sql(primary, "nemotron", "SCHEMA", "q")
    assert sql == "SELECT 'claude'" and primary.calls == 0
    assert aa.get_last_tier_used() == "claude"
    assert aa.get_last_claude_model() == "claude-sonnet-5-5"
    assert aa.provider_of("claude") == "anthropic"
    assert usage["prompt_tokens"] == 110


def test_generate_sql_falls_through_to_the_old_chain(monkeypatch):
    _install(
        monkeypatch,
        {
            "claude-sonnet-5-5": (401, {"type": "authentication_error", "message": "bad"}),
            "claude-haiku-5-5": (401, {"type": "authentication_error", "message": "bad"}),
        },
    )
    primary = _FakeOpenAI()
    aa.begin_request_tier_tracking()
    sql, _, _ = aa.generate_sql(primary, "nemotron", "SCHEMA", "q")
    assert sql == "SELECT 'openrouter'" and primary.calls == 1
    assert aa.get_last_tier_used() == aa.get_primary_tier()


def test_a_timeout_stops_claude_for_the_call_and_benches_it(monkeypatch):
    calls = []

    def _slow(c, m):
        def _call():
            calls.append(m)
            raise anthropic.APITimeoutError(request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))

        return _call

    _install(monkeypatch, {})
    assert cp.call_first(_slow) is None
    assert calls == ["claude-sonnet-5-5"]  # Haiku does not get a fresh wait
    assert cp.is_latched()
    assert cp.call_first(_slow) is None and calls == ["claude-sonnet-5-5"]


def test_one_budget_is_shared_across_the_ranked_models(monkeypatch):
    """Sonnet's 529 arrives after the budget is spent: Haiku is not tried."""
    monkeypatch.setenv("CLAUDE_TIMEOUT_SECONDS", "5")
    now = [1000.0]
    monkeypatch.setattr(cp.time, "monotonic", lambda: now[0])
    server = _install(
        monkeypatch,
        {
            "claude-sonnet-5-5": (529, {"type": "overloaded_error", "message": "busy"}),
            "claude-haiku-5-5": (200, _message(model="claude-haiku-5-5")),
        },
    )

    def _slow_sql_call(c, m):
        call = _sql_call(c, m)

        def _run():
            try:
                return call()
            finally:
                now[0] += 6

        return _run

    assert cp.call_first(_slow_sql_call) is None
    assert [r["model"] for r in server.requests] == ["claude-sonnet-5-5"]


def test_usage_has_no_claude_entry_without_a_key(monkeypatch):
    import app

    assert "anthropic" not in app.get_usage_summary()["providers"]
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    assert "anthropic" in app.get_usage_summary()["providers"]
