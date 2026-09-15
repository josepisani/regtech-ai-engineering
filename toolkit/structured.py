"""structured.py — call a model with a schema, get back a validated object.

WHAT IT DOES
    One function, `call_schema`. You hand it a Pydantic class and a prompt; it
    hands back an instance of that class, or raises. Never a dict, never a
    string that "should" be JSON, never a half-filled object.

WHY IT EXISTS
    The Anthropic API enforces a JSON schema during generation, so most of the
    time the reply already conforms. Most of the time is not every time, and
    two documented paths break it:
        stop_reason == "max_tokens"  -> the JSON is cut off mid-structure
        stop_reason == "refusal"     -> a refusal message replaces the schema
    A third reason is portability: providers without a grammar (and older
    models) need the validate-and-retry belt, and keeping it here means the
    call sites in Projects 1-3 never change when the provider does.

    The retry feeds the *exact* validation error back to the model. A blind
    retry just re-rolls the dice; a retry that says "confidence must be one of
    low/medium/high, you sent 'quite sure'" usually gets fixed on attempt two.

HOW TO CALL IT
    from toolkit.structured import call_schema

    result = call_schema(
        MyModel,
        prompt="...",
        system="You are ...",
        model="claude-haiku-4-5",
    )
    result.data          # -> MyModel instance
    result.attempts      # -> 1, or more if it had to retry
    result.usage         # -> tokens summed over EVERY attempt; costlog prices it

    A failure is billed too. RefusalError and SchemaRetryError carry the same
    `usage` (and `model`) for the responses received before giving up, so the
    caller can record what a failed classification cost.

WHAT IT DELIBERATELY DOES NOT DO
    It does not price the call. Pricing lives in one place or it eventually
    lives in two places that disagree; that place is `toolkit/costlog.py`,
    promoted on Day 3. `result.usage` is passed through for it to read, cache
    buckets included.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Any, TypeVar

from anthropic import Anthropic, transform_schema
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

DEFAULT_MODEL = "claude-haiku-4-5"

# Models that still accept sampling parameters. The 5-series rejects them
# outright (400), and anthropic 1.x dropped them from the typed method
# signature, so they have to travel via extra_body. Same set and same reasoning
# as src/llm_probe.py — see the note in START-HERE.md §2.
TEMPERATURE_MODELS = {
    "claude-haiku-4-5",
    "claude-haiku-4-5-20251001",
    "claude-sonnet-4-6",
    "claude-opus-4-6",
    "claude-sonnet-4-5",
    "claude-opus-4-5",
}


# Prompt caching has a minimum block size, below which cache_control is
# accepted and then silently ignored — you get no error and no cache, which is
# the worst possible failure mode because it looks like it worked. The minimum
# is model-dependent (2048 tokens on the Haiku line, 1024 on Sonnet/Opus), so
# the guard below uses the larger figure and warns rather than raises: a block
# that is too small is a wasted optimisation, not a broken call.
MIN_CACHEABLE_TOKENS = 2048
_CHARS_PER_TOKEN = 4  # rough; only used to decide whether to warn


def cached_system(*blocks: str, cache_last: bool = True) -> list[dict[str, Any]]:
    """Build a system prompt as content blocks, with a cache breakpoint.

    Prompt caching charges the marked prefix once (at a premium) and then reads
    it back at a tenth of the input price on every later call that repeats it
    byte for byte. For this project that matters more than it usually does:
    Day 3's measurement showed ~7.2k input tokens per classification, of which
    the description is ~300 — 94% of what we pay for on every row is the same
    instructions and the same five worked examples.

    ORDER MATTERS, and it is the easy thing to get wrong. Everything BEFORE the
    breakpoint is cached, so anything that varies per call must come after it,
    or the prefix changes and the cache misses every time. That is why the
    per-description text goes in the user message and never in here.

    Args:
        *blocks: system prompt sections, in order.
        cache_last: put the breakpoint on the final block, so every block is
            cached. Set False to send the blocks uncached (useful for an A/B
            measurement of what caching is actually saving).

    Returns:
        A list of content-block dicts suitable for `system=`.
    """
    out: list[dict[str, Any]] = [{"type": "text", "text": b} for b in blocks if b]
    if not out or not cache_last:
        return out

    total_chars = sum(len(b["text"]) for b in out)
    if total_chars < MIN_CACHEABLE_TOKENS * _CHARS_PER_TOKEN:
        warnings.warn(
            f"System prompt is ~{total_chars // _CHARS_PER_TOKEN} tokens, below the "
            f"~{MIN_CACHEABLE_TOKENS}-token cache minimum. cache_control will be "
            f"ignored silently and you will pay full input price. Check "
            f"cache_read_input_tokens in the usage before trusting a saving figure.",
            stacklevel=2,
        )

    out[-1]["cache_control"] = {"type": "ephemeral"}
    return out


@dataclass
class Usage:
    """Token counts summed over every response received during one call.

    A classification that truncates, retries and then succeeds has made three
    billable calls, and the first two do not become free because the third
    worked. So `call_schema` adds every response it receives into one of these
    and hands it back on the result when it succeeds and on the exception when
    it does not. The four attribute names are the SDK's own, so
    `costlog.price` reads this exactly as it would read one raw usage object.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    responses: int = 0

    def add(self, usage: Any) -> None:
        """Add one response's usage. Absent and None fields count as zero."""
        for name in (
            "input_tokens",
            "output_tokens",
            "cache_creation_input_tokens",
            "cache_read_input_tokens",
        ):
            setattr(self, name, getattr(self, name) + int(getattr(usage, name, 0) or 0))
        self.responses += 1


class StructuredError(RuntimeError):
    """Base class, so a caller can catch every failure of this module at once.

    `usage` is what the failed call cost: every response received before the
    error, summed. A caller that records spend must record this too, or a
    request that fails three times in a row costs three calls and counts as
    nothing. It is None only when no response was ever received.
    """

    def __init__(
        self, message: str, *, usage: Usage | None = None, model: str | None = None
    ) -> None:
        super().__init__(message)
        self.usage = usage
        self.model = model


class RefusalError(StructuredError):
    """The model declined to answer.

    Raised immediately without retrying: a refusal is a decision about the
    content, not a formatting slip, so asking again in the same words spends
    money to receive the same answer.
    """


class SchemaRetryError(StructuredError):
    """Ran out of attempts without a conforming answer.

    This is the honest end of the road: no partial object is returned and no
    field is defaulted, because a pipeline that silently invents a value when
    the model failed will never show you that it happened.

    The last validation error is kept on `last_error`, NOT in the message.
    Pydantic quotes the rejected value in its error text, and on this project
    the rejected value can be a field the model filled from the user's
    description — so `str(exc)` must stay safe to show, and the detail stays
    on the attribute for whoever is debugging locally.
    """

    def __init__(
        self,
        attempts: int,
        last_error: str,
        *,
        usage: Usage | None = None,
        model: str | None = None,
    ) -> None:
        super().__init__(
            f"No schema-conformant response after {attempts} attempt(s).",
            usage=usage,
            model=model,
        )
        self.attempts = attempts
        self.last_error = last_error


@dataclass
class StructuredResult:
    """What came back, plus what it took to get it.

    `attempts` is worth logging even when it is 1 — a schema whose attempt
    count creeps up over time is telling you the prompt and the schema have
    drifted apart, and that is much easier to see in a number than in prose.

    `usage` covers every attempt, not just the one that succeeded.
    """

    data: BaseModel
    attempts: int
    usage: Usage
    stop_reason: str | None
    model: str


def call_schema(
    schema: type[T],
    *,
    prompt: str,
    system: str | list[dict[str, Any]] | None = None,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 2048,
    max_attempts: int = 3,
    temperature: float | None = None,
    client: Anthropic | None = None,
) -> StructuredResult:
    """Return an instance of `schema`, retrying on invalid output.

    Args:
        schema: a Pydantic model class. Its JSON Schema is what constrains
            generation, so the class is the contract for both ends of the call.
        prompt: the user message.
        system: optional system prompt. A plain string, or a list of content
            blocks when you want prompt caching — see `cached_system`. The list
            form is passed straight through, so a caller can mark exactly which
            blocks are cacheable and this module stays out of that decision.
        model: model id. Defaults to Haiku 4.5 — the cheap one, per the sprint's
            standing rule that experiments run on Haiku.
        max_tokens: doubled on each retry after a truncation, because
            retrying a truncated answer with the same ceiling truncates again.
        max_attempts: total tries, not extra tries. 3 is enough; if a schema
            needs more, the schema or the prompt is the problem.
        temperature: sent only for models that still accept it, otherwise
            warned about and dropped.
        client: inject one to reuse a connection or to pass a fake in a test.

    Raises:
        RefusalError: the model declined.
        SchemaRetryError: attempts exhausted.
    """
    client = client or Anthropic()

    # The schema travels as an output_config, built the same way the SDK's
    # messages.parse() builds it — but sent through messages.create(), which
    # returns the message RAW. That difference is the whole point of this
    # function. parse() validates the reply against the schema before it
    # returns, so a reply cut off at max_tokens raises a ValidationError
    # inside the SDK and the stop_reason checks below never run. Found in the
    # 2026-09-15 review: the wrapper called parse(), and its retry loop could
    # only be reached by a fake that skipped the SDK's own validation.
    output_config = {
        "format": {
            "type": "json_schema",
            "schema": transform_schema(schema.model_json_schema()),
        }
    }

    # The conversation grows across attempts: each failed reply and the error it
    # caused stay in the messages list, so the model can see its own mistake.
    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
    last_error = "no attempt was made"
    tokens = max_tokens
    usage = Usage()

    for attempt in range(1, max_attempts + 1):
        params: dict[str, Any] = {
            "model": model,
            "max_tokens": tokens,
            "messages": messages,
            "output_config": output_config,
        }
        if system:
            params["system"] = system
        if temperature is not None:
            if model in TEMPERATURE_MODELS:
                params["extra_body"] = {"temperature": temperature}
            else:
                warnings.warn(
                    f"{model} does not accept temperature; dropping "
                    f"temperature={temperature}. Determinism here comes from "
                    f"the schema, not from sampling.",
                    stacklevel=2,
                )

        message = client.messages.create(**params)
        # Billed the moment it arrives, whatever it turns out to contain.
        usage.add(message.usage)

        # --- stop_reason is checked before the payload ---------------------
        # A truncated or refused response can still carry something that looks
        # parseable, so reading the payload first would mean trusting a
        # fragment. The classic structured-output bug is a JSON object cut off
        # at max_tokens and reported as a mysterious schema error.
        if message.stop_reason == "refusal":
            raise RefusalError(
                "The model refused to answer this prompt. Retrying the same "
                "prompt will not change that.",
                usage=usage,
                model=model,
            )

        if message.stop_reason == "max_tokens":
            last_error = f"response truncated at max_tokens={tokens}"
            tokens *= 2
            messages = [{"role": "user", "content": prompt}]  # start clean
            continue

        # --- the payload ---------------------------------------------------
        # Validated HERE, by us, after the stop_reason is known. The grammar
        # means the text usually conforms already; validating it locally is
        # what makes this wrapper work unchanged against a provider with no
        # structured-output support, and what puts a malformed reply into the
        # retry below instead of into an exception from inside the SDK.
        # model_validate_json raises the same ValidationError for text that is
        # not JSON at all as for JSON that breaks the schema.
        raw = "".join(
            block.text for block in message.content if getattr(block, "type", None) == "text"
        )
        try:
            return StructuredResult(
                data=schema.model_validate_json(raw),
                attempts=attempt,
                usage=usage,
                stop_reason=message.stop_reason,
                model=model,
            )
        except ValidationError as exc:
            last_error = str(exc)
            # Feed the failure back: the assistant's own words, then the precise
            # complaint. This is the part that makes a retry worth paying for.
            messages = messages + [
                {"role": "assistant", "content": raw or "(empty response)"},
                {
                    "role": "user",
                    "content": (
                        "That response did not match the required schema.\n\n"
                        f"Error:\n{last_error}\n\n"
                        "Return the corrected object. Change only what the "
                        "error names; keep every other field as it was."
                    ),
                },
            ]

    raise SchemaRetryError(max_attempts, last_error, usage=usage, model=model)
