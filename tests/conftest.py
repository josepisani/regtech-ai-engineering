"""Shared test fixtures, and the fake client that makes the offline tests possible.

THE SPLIT THIS FILE EXISTS TO ENFORCE
    Two kinds of edge case, and conflating them is how a test suite becomes
    something you stop running.

    OFFLINE tests need no key, no network and no money. They cover everything
    that is our own Python: the input guards, the truncation and refusal paths,
    the pricing arithmetic, and the Act gates that are decided in Python rather
    than by the model (the Annex III 5(b) carve-out, the Article 6(3) profiling
    override, the Article 25 escalation). These run on every commit.

    LIVE tests call the real model, cost real money and can fail for reasons
    that are not regressions. They are marked `live` and skipped unless
    ANTHROPIC_API_KEY is set AND you ask for them:

        pytest                       # offline only
        pytest -m live               # the four model-behaviour cases
        pytest -m "not live"         # explicit, same as the default

    Keeping them apart means a red suite always means a real defect.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "live: hits the real Anthropic API; costs money; needs ANTHROPIC_API_KEY"
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip live tests unless they were explicitly asked for.

    Two conditions, both required. Having the key is not consent to spend it,
    so `-m live` is the ask; and asking without a key should say so plainly
    rather than fail with an auth error twenty seconds later.
    """
    asked_for_live = "live" in (config.getoption("-m") or "")
    if asked_for_live and not os.getenv("ANTHROPIC_API_KEY"):
        pytest.exit("Live tests were requested but ANTHROPIC_API_KEY is not set.", returncode=1)
    if asked_for_live:
        return
    skip = pytest.mark.skip(reason="live test; run with -m live and an API key set")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)


def usage(
    input_tokens: int = 1_000,
    output_tokens: int = 200,
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0,
) -> SimpleNamespace:
    """A stand-in for the SDK's usage object.

    SimpleNamespace rather than a Mock on purpose: a Mock answers every
    attribute, so a typo in a field name would pass silently and price
    something that does not exist.
    """
    return SimpleNamespace(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_creation_input_tokens=cache_creation_input_tokens,
        cache_read_input_tokens=cache_read_input_tokens,
    )


def text_block(text: str) -> SimpleNamespace:
    """One text content block, shaped like the SDK's."""
    return SimpleNamespace(type="text", text=text)


@dataclass
class FakeMessage:
    """A raw API message: what messages.create() returns, before any parsing.

    There is deliberately no `parsed_output` field. The first version of this
    fake had one, and the wrapper read it — which meant the fake handed over
    an already-validated object at a point where the real SDK would already
    have raised on a truncated reply. Scripting the TEXT the model sent, and
    nothing more, keeps the fake on the same side of the boundary as
    production.
    """

    stop_reason: str | None
    content: list[Any] = None  # type: ignore[assignment]
    usage: Any = None

    def __post_init__(self) -> None:
        if self.content is None:
            self.content = []
        if self.usage is None:
            self.usage = usage()


class FakeClient:
    """Replays a scripted list of messages at the SDK boundary.

    `messages.create` returns the next scripted message raw, as the real one
    does. `messages.parse` does what the real one does too: it validates every
    text block against `output_format` BEFORE returning and raises
    ValidationError when the text does not conform — which is exactly what a
    reply cut off at max_tokens is. Any code that goes back to calling parse()
    therefore fails the truncation test, as the production path did until the
    2026-09-15 review. Emulate the boundary; never bypass it.

    It also records the params it was called with, which is how the caching
    test checks that the system prompt really carried a cache_control marker —
    the only way to verify that offline, since the saving itself only shows up
    in a real response's usage.
    """

    def __init__(self, *responses: FakeMessage) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []
        self.messages = SimpleNamespace(create=self._create, parse=self._parse)

    def _create(self, **params: Any) -> FakeMessage:
        self.calls.append(params)
        if not self._responses:
            raise AssertionError(
                f"FakeClient ran out of scripted responses after {len(self.calls)} call(s). "
                "The code under test retried more times than the test expected."
            )
        return self._responses.pop(0)

    def _parse(self, **params: Any) -> FakeMessage:
        from pydantic import TypeAdapter

        output_format = params.pop("output_format", None)
        message = self._create(**params)
        if output_format is not None:
            for block in message.content:
                if getattr(block, "type", None) == "text":
                    TypeAdapter(output_format).validate_json(block.text)  # raises, as the SDK does
        return message


@pytest.fixture
def verdict_dict() -> dict[str, Any]:
    """A complete, valid ModelVerdict payload: the TalentFirst example.

    Tests mutate a copy of this rather than building a verdict from scratch, so
    adding a required field to the schema breaks one fixture instead of ten
    tests — and breaks it loudly, which is the point.
    """
    return {
        "system_name": "TalentFirst AI Screener",
        "provider_name": "TalentFirst",
        "system_purpose": "Ranks and scores job applicants' CVs to produce a shortlist.",
        "act_applies": "applies",
        "exclusion_ground": "none",
        "our_role": "deployer",
        "art25_trigger": "none",
        "risk_tier": "high_risk",
        "annex_iii_derogation": "none",
        "performs_profiling": True,
        "is_gpai": False,
        "gpai_note": None,
        "legal_basis": ["Annex III 4(a)"],
        "rationale": "Recruitment and candidate evaluation is the Annex III 4(a) use case.",
        "gaps": ["Does the vendor supply instructions for use?"],
        "confidence": "high",
    }
