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
    result.usage         # -> raw usage object; Day 3's costlog prices it

WHAT IT DELIBERATELY DOES NOT DO
    It does not price the call. Pricing lives in one place or it eventually
    lives in two places that disagree; Day 3 promotes `toolkit/costlog.py` and
    that becomes the single table. Until then `result.usage` is passed through.
"""
from __future__ import annotations

import json
import warnings
from dataclasses import dataclass
from typing import Any, TypeVar

from anthropic import Anthropic
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


class StructuredError(RuntimeError):
    """Base class, so a caller can catch every failure of this module at once."""


class RefusalError(StructuredError):
    """The model declined to answer.

    Raised immediately without retrying: a refusal is a decision about the
    content, not a formatting slip, so asking again in the same words spends
    money to receive the same answer.
    """


class SchemaRetryError(StructuredError):
    """Ran out of attempts without a conforming answer.

    Carries the last error so the failure can be read after the fact instead of
    guessed at. This is the honest end of the road: no partial object is
    returned and no field is defaulted, because a pipeline that silently
    invents a value when the model failed will never show you that it happened.
    """

    def __init__(self, attempts: int, last_error: str) -> None:
        super().__init__(
            f"No schema-conformant response after {attempts} attempt(s). "
            f"Last error: {last_error}"
        )
        self.attempts = attempts
        self.last_error = last_error


@dataclass
class StructuredResult:
    """What came back, plus what it took to get it.

    `attempts` is worth logging even when it is 1 — a schema whose attempt
    count creeps up over time is telling you the prompt and the schema have
    drifted apart, and that is much easier to see in a number than in prose.
    """

    data: BaseModel
    attempts: int
    usage: Any
    stop_reason: str | None
    model: str


def call_schema(
    schema: type[T],
    *,
    prompt: str,
    system: str | None = None,
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
        system: optional system prompt.
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

    # The conversation grows across attempts: each failed reply and the error it
    # caused stay in the messages list, so the model can see its own mistake.
    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
    last_error = "no attempt was made"
    tokens = max_tokens

    for attempt in range(1, max_attempts + 1):
        params: dict[str, Any] = {
            "model": model,
            "max_tokens": tokens,
            "messages": messages,
            "output_format": schema,
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

        message = client.messages.parse(**params)

        # --- stop_reason is checked before the payload ---------------------
        # A truncated or refused response can still carry something that looks
        # parseable, so reading the payload first would mean trusting a
        # fragment. The classic structured-output bug is a JSON object cut off
        # at max_tokens and reported as a mysterious schema error.
        if message.stop_reason == "refusal":
            raise RefusalError(
                "The model refused to answer this prompt. Retrying the same "
                "prompt will not change that."
            )

        if message.stop_reason == "max_tokens":
            last_error = f"response truncated at max_tokens={tokens}"
            tokens *= 2
            messages = [{"role": "user", "content": prompt}]  # start clean
            continue

        # --- the payload ---------------------------------------------------
        # parsed_output is already an instance of `schema` when the grammar did
        # its job. It can be None if the reply carried no parseable block, so
        # the fallback re-parses the raw text: that path is what makes this
        # wrapper work against a provider with no structured-output support.
        parsed = getattr(message, "parsed_output", None)
        if parsed is not None:
            return StructuredResult(
                data=parsed,
                attempts=attempt,
                usage=message.usage,
                stop_reason=message.stop_reason,
                model=model,
            )

        raw = "".join(
            block.text for block in message.content if getattr(block, "type", None) == "text"
        )
        try:
            return StructuredResult(
                data=schema.model_validate(json.loads(raw)),
                attempts=attempt,
                usage=message.usage,
                stop_reason=message.stop_reason,
                model=model,
            )
        except (json.JSONDecodeError, ValidationError) as exc:
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

    raise SchemaRetryError(max_attempts, last_error)
