"""Claude (Anthropic API) as the first-choice LLM provider.

Sits IN FRONT of the existing OpenRouter -> Cerebras chain rather than inside
it: every call tries Claude first, and any Claude failure hands the same call
to the untouched two-provider machinery in analytics_agent (its retry ladder,
latches, model-deprecation pinning and swapped refine). Unset
ANTHROPIC_API_KEY and none of this runs — the bot is exactly what it was.

The rest of the app reads OpenAI-shaped responses (`choices[0].message.content`,
streamed `choices[0].delta.content`, `usage.prompt_tokens`), so ClaudeClient
answers in that shape. It is NOT an OpenAI-compatible endpoint: every request
goes through the official `anthropic` SDK to POST /v1/messages, and the
translation lives here:

  * system-role messages -> the top-level `system` field (cached, see below);
  * `temperature` is dropped — current Claude models reject non-default
    sampling parameters with a 400;
  * `max_tokens` gets a floor, because adaptive thinking spends from the same
    budget before the answer starts;
  * `stop_reason == "refusal"` and an answer with no text both raise, so the
    call falls through to the next provider instead of serving nothing.

Model choice (CLAUDE_MODELS, ranked): Sonnet 5.5 first, Haiku 5.5 behind it,
both at effort `low`. The bot's calls are NL->SQL against a large schema plus
two short prose passes; SQL correctness is the accuracy that matters and
Sonnet is the tier built for it, while `low` effort keeps thinking — and so
time-to-first-token — short. Haiku 5.5 is the faster/cheaper rung, used when
Sonnet is overloaded or retired. Re-rank with eval/run_eval.py
--provider claude before changing the order.
"""

import logging
import os
import threading
import time
from types import SimpleNamespace

log = logging.getLogger("analytics")

DEFAULT_CLAUDE_MODELS = ["claude-sonnet-5-5", "claude-haiku-5-5"]
DEFAULT_CLAUDE_EFFORT = "low"
# Adaptive thinking draws on max_tokens before any answer text, so the callers'
# budgets (sized for non-thinking models: 1,200 for the background note) would
# truncate. Billing is per token produced, not per token allowed.
MIN_MAX_TOKENS = 8192

TIER = "claude"


def api_key() -> str:
    return os.environ.get("ANTHROPIC_API_KEY", "")


def is_configured() -> bool:
    return bool(api_key())


def models() -> list:
    env = os.environ.get("CLAUDE_MODELS", "")
    if env.strip():
        return [m.strip() for m in env.split(",") if m.strip()]
    return list(DEFAULT_CLAUDE_MODELS)


def effort() -> str:
    return os.environ.get("CLAUDE_EFFORT", DEFAULT_CLAUDE_EFFORT) or DEFAULT_CLAUDE_EFFORT


class ClaudeRefusal(RuntimeError):
    """stop_reason == 'refusal': a safety classifier declined the request."""


class ClaudeEmpty(RuntimeError):
    """The response carried no answer text (e.g. thinking used the budget)."""


# ── Unusable latch ──────────────────────────────────────────────────────────
# Same idea as analytics_agent's primary latch, kept separate because it
# describes a different provider: a bad key, an unscoped key or an empty credit
# balance fails every call identically until a human acts, so skip Claude for
# a while instead of paying a doomed round trip three times per question.
RECHECK_SECONDS = 900
_unusable_at = None
# A model the API says does not exist is skipped (ranked list moves on) until
# the same recheck; per model, so retiring Sonnet does not bench Haiku.
_dead_models: dict = {}
_lock = threading.Lock()


def is_latched() -> bool:
    return _unusable_at is not None and (time.time() - _unusable_at) < RECHECK_SECONDS


def _latch(on: bool = True) -> None:
    global _unusable_at
    _unusable_at = time.time() if on else None


def _model_is_dead(model: str) -> bool:
    at = _dead_models.get(model)
    return at is not None and (time.time() - at) < RECHECK_SECONDS


def live_models() -> list:
    return [m for m in models() if not _model_is_dead(m)]


def is_durable_failure(e: Exception) -> bool:
    """Fails the same way on every call until a human fixes the account."""
    import anthropic
    if isinstance(e, (anthropic.AuthenticationError, anthropic.PermissionDeniedError)):
        return True
    if getattr(e, "status_code", None) == 402:
        return True
    if isinstance(e, anthropic.BadRequestError):
        s = str(e).lower()
        # "Your credit balance is too low ..." and the unscoped-key 400
        # ("not scoped to a workspace ... anthropic-workspace-id header").
        return "credit balance" in s or "workspace" in s
    return False


def _is_model_gone(e: Exception) -> bool:
    import anthropic
    return isinstance(e, anthropic.NotFoundError)


def _is_overloaded(e: Exception) -> bool:
    import anthropic
    return (isinstance(e, anthropic.RateLimitError)
            or getattr(e, "status_code", None) in (500, 502, 503, 529)
            or isinstance(e, anthropic.APIConnectionError))


# ── Request/response translation ───────────────────────────────────────────

def _split_messages(messages: list):
    """OpenAI chat messages -> (system blocks, Claude messages).

    The system text is marked for prompt caching: it is the schema-bearing
    prompt (the bulk of every request's input) and identical across
    questions, so repeat questions read it from cache — cheaper and faster.
    Below the model's minimum cacheable length the marker is simply ignored."""
    system_parts, out = [], []
    for m in messages:
        role, content = m.get("role"), m.get("content") or ""
        if role == "system":
            system_parts.append(content)
        elif role in ("user", "assistant"):
            if out and out[-1]["role"] == role:
                out[-1]["content"] += "\n\n" + content
            else:
                out.append({"role": role, "content": content})
    # The API needs a user turn first; history can start with an assistant turn.
    while out and out[0]["role"] != "user":
        out.pop(0)
    system = None
    if system_parts:
        system = [{"type": "text", "text": "\n\n".join(system_parts),
                   "cache_control": {"type": "ephemeral"}}]
    return system, out


def _usage_ns(usage) -> SimpleNamespace:
    if usage is None:
        return SimpleNamespace(prompt_tokens=0, completion_tokens=0, total_tokens=0)
    prompt = ((getattr(usage, "input_tokens", 0) or 0)
              + (getattr(usage, "cache_read_input_tokens", 0) or 0)
              + (getattr(usage, "cache_creation_input_tokens", 0) or 0))
    completion = getattr(usage, "output_tokens", 0) or 0
    return SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion,
                           total_tokens=prompt + completion)


def _check_stop(stop_reason, text: str) -> None:
    if stop_reason == "refusal":
        raise ClaudeRefusal("Claude declined the request (stop_reason=refusal)")
    if not text or not text.strip():
        raise ClaudeEmpty(f"Claude returned no answer text (stop_reason={stop_reason})")


def _to_openai_shape(message) -> SimpleNamespace:
    text = "".join(b.text for b in message.content if b.type == "text")
    _check_stop(message.stop_reason, text)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text),
                                 finish_reason=message.stop_reason)],
        usage=_usage_ns(message.usage),
        model=message.model,
    )


def _chunk(text: str) -> SimpleNamespace:
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text))])


class _StreamAdapter:
    """Iterates a raw Messages event stream as OpenAI-style chunks.

    Every event yields a chunk — empty for thinking, pings and bookkeeping —
    so analytics_agent's stall guard measures whether Claude is alive, not
    whether it has started writing prose yet. Callers skip empty content."""

    def __init__(self, stream, model: str):
        self._stream = stream
        self._model = model

    def close(self):
        self._stream.close()

    def __iter__(self):
        stop_reason, wrote = None, False
        for event in self._stream:
            if event.type == "content_block_delta" and event.delta.type == "text_delta":
                wrote = wrote or bool(event.delta.text.strip())
                yield _chunk(event.delta.text)
                continue
            if event.type == "message_delta":
                stop_reason = event.delta.stop_reason
            yield _chunk("")
        _check_stop(stop_reason, "x" if wrote else "")


def _log_call(model: str, headers, usage=None) -> None:
    """Per-call accounting line: which workspace was billed, and the request
    id Anthropic support asks for. Never the key."""
    headers = headers or {}
    log.info("Claude call: model=%s request-id=%s workspace=%s usage=%s",
             model, headers.get("request-id"), headers.get("anthropic-workspace-id"),
             None if usage is None else dict(input=usage.prompt_tokens, output=usage.completion_tokens))


class _RawResponse:
    """Stands in for openai's LegacyAPIResponse: `.parse()` and `.headers`."""

    def __init__(self, parsed, headers):
        self._parsed, self.headers = parsed, headers

    def parse(self):
        return self._parsed


class _Completions:
    def __init__(self, owner, raw: bool):
        self._owner, self._raw = owner, raw

    def create(self, *, model, messages, max_tokens=4096, stream=False, temperature=None, **_):
        del temperature  # rejected by current models; see module docstring
        sdk = self._owner._sdk
        system, msgs = _split_messages(messages)
        params = dict(model=model, max_tokens=max(max_tokens or 0, MIN_MAX_TOKENS),
                      messages=msgs, output_config={"effort": effort()})
        if system:
            params["system"] = system
        if stream:
            raw = sdk.messages.with_raw_response.create(stream=True, **params)
            _log_call(model, raw.headers)
            return _StreamAdapter(raw.parse(), model)
        raw = sdk.messages.with_raw_response.create(**params)
        resp = _to_openai_shape(raw.parse())
        _log_call(model, raw.headers, resp.usage)
        return _RawResponse(resp, raw.headers) if self._raw else resp


class ClaudeClient:
    """The slice of `openai.OpenAI` analytics_agent uses, served by Claude."""

    def __init__(self, sdk):
        self._sdk = sdk
        self.chat = SimpleNamespace(completions=_Completions(self, raw=False))
        self.with_raw_response = SimpleNamespace(
            chat=SimpleNamespace(completions=_Completions(self, raw=True)))

    def with_options(self, **kw) -> "ClaudeClient":
        return ClaudeClient(self._sdk.with_options(**kw))


_client = None


def get_client(timeout: float = 60.0):
    """The shared ClaudeClient, or None when ANTHROPIC_API_KEY is unset.

    max_retries=0 like the other providers' clients: a failure moves to the
    next Claude model, then to OpenRouter/Cerebras, which beats the SDK
    sleeping and retrying the same overloaded endpoint while a user waits."""
    global _client
    if not is_configured():
        return None
    with _lock:
        if _client is None:
            import anthropic
            _client = ClaudeClient(anthropic.Anthropic(
                api_key=api_key(), max_retries=0,
                timeout=anthropic.Timeout(timeout, connect=10.0)))
        return _client


def call_first(make_call):
    """Try `make_call(client, model)()` on Claude, model by model in rank order.

    Returns (result, model) on success, or None when Claude is not configured,
    latched out, or every model failed — the caller then runs its normal
    provider chain. Never raises: Claude is an optimisation in front of a
    working chain, so its failures are logged and swallowed."""
    client = get_client(_timeout())
    if client is None or is_latched():
        return None
    for model in live_models():
        try:
            return make_call(client, model)(), model
        except Exception as e:  # noqa: BLE001 — every failure falls through
            if is_durable_failure(e):
                log.error("Claude unusable (%s: %s); skipping it for %ds",
                          type(e).__name__, e, RECHECK_SECONDS)
                _latch()
                return None
            if _is_model_gone(e):
                log.error("Claude model '%s' not found; skipping it for %ds", model, RECHECK_SECONDS)
                _dead_models[model] = time.time()
                continue
            if _is_overloaded(e):
                log.warning("Claude model '%s' unavailable (%s); trying the next", model, type(e).__name__)
                continue
            # Refusal, empty answer, a 400 for this request: another Claude
            # model would most likely do the same; the other providers might not.
            log.warning("Claude call failed (%s: %s); using the fallback providers", type(e).__name__, e)
            return None
    return None


def _timeout() -> float:
    return float(os.environ.get("LLM_TIMEOUT_SECONDS", "60") or 60)


def is_claude_error(e: Exception) -> bool:
    """A Claude failure that escaped call_first — only possible mid-stream,
    after the call had already been handed to the caller."""
    if isinstance(e, (ClaudeRefusal, ClaudeEmpty)):
        return True
    try:
        import anthropic
    except ImportError:
        return False
    return isinstance(e, anthropic.APIError)
