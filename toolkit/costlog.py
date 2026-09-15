"""costlog.py — price one model call, and write a line about it that is safe to keep.

WHAT IT DOES
    price(usage, model)        -> Cost, the four token buckets in dollars
    log_call(...)              -> appends one JSON line to the call log
    summarise(costs)           -> totals for a batch (compare.py, evals, the UI)

WHY IT EXISTS
    Two reasons, and the second is the one that bites later.

    1. Pricing must live in ONE place. src/llm_probe.py and src/aiact/compare.py
       both grew their own arithmetic; the moment those disagree, every cost
       number in the README becomes untrustworthy and there is no way to tell
       which one was wrong. This module is now the single table. llm_probe.py
       keeps its own copy on purpose — it is the standalone teaching file — but
       nothing else should.

    2. A cost log is the first thing that quietly starts storing user input.
       The natural line to write is {"description": ..., "cost": ...}, because
       that is what you want when you are debugging. On a public paste box that
       makes you a GDPR controller of whatever a stranger pasted — a CV, a
       client name, an incident report. So this module cannot write it: there
       is no parameter for the text, and `char_count` is offered instead. That
       is a design decision, not an oversight, and it is why the no-logging
       rule is built on Day 3 rather than removed on Day 4.

HOW TO USE IT
    from toolkit.costlog import price, log_call

    record, result = classify_with_meta(text)
    cost = price(result.usage, result.model)
    log_call(result, latency_s=elapsed, char_count=len(text))

    print(cost.total_usd, cost.cache_saved_usd)

WHAT IT DELIBERATELY DOES NOT DO
    It does not import anthropic, fastapi or streamlit, and it does not know
    what a Classification is. It takes a usage object with the four documented
    integer attributes and returns numbers. That is why it can be called from
    a CLI, an API handler, a Streamlit page and a test with a fake object.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

# --- Prices -----------------------------------------------------------------
# USD per *token*, with the published $/1M figure left visible in the
# arithmetic so it can be checked against the pricing page without decoding a
# float. Same convention as src/llm_probe.py.
#
# The two cache buckets are derived from the base input price rather than typed
# in, because they are defined as multiples of it:
#     cache WRITE (5-minute ephemeral) = 1.25x input   -- you pay a premium once
#     cache READ                       = 0.10x input   -- then a tenth thereafter
# The 0.10x read multiplier is confirmed by START-HERE.md's price table
# (Haiku 4.5: $1.00 input, $0.10 cache read). The 1.25x write multiplier is the
# documented default for the 5-minute TTL and is the one number in this file
# NOT yet checked against the pricing page — verify it before any cost figure
# from this module reaches a README. A wrong write multiplier overstates or
# understates the first call of a session and nothing else.
CACHE_WRITE_MULTIPLIER = 1.25
CACHE_READ_MULTIPLIER = 0.10

PRICING: dict[str, dict[str, float]] = {
    "claude-fable-5":   {"input": 10.00 / 1_000_000, "output": 50.00 / 1_000_000},
    "claude-opus-5":    {"input":  5.00 / 1_000_000, "output": 25.00 / 1_000_000},
    "claude-sonnet-5":  {"input":  2.00 / 1_000_000, "output": 10.00 / 1_000_000},
    "claude-haiku-4-5": {"input":  1.00 / 1_000_000, "output":  5.00 / 1_000_000},
}

# Where log_call writes. Overridable so a test never touches the real file and
# so Cloud Run can point it at stdout instead of a path (see log_call).
CALL_LOG_PATH = Path(os.getenv("CALL_LOG_PATH", "data/call_log.jsonl"))


class UnknownModelError(KeyError):
    """No price for that model id.

    Raised rather than defaulted. A silently mispriced call is worse than a
    crash, because it produces a number that looks like evidence.
    """


@dataclass(frozen=True)
class Cost:
    """One call, priced. All figures USD.

    `cache_saved_usd` is the honest form of the caching win: what the cached
    tokens WOULD have cost at the full input price, minus what they actually
    cost. It is a saving against the uncached counterfactual, not money back.
    """

    model: str
    input_tokens: int
    output_tokens: int
    cache_write_tokens: int
    cache_read_tokens: int
    input_usd: float
    output_usd: float
    cache_write_usd: float
    cache_read_usd: float
    total_usd: float
    cache_saved_usd: float

    @property
    def billed_input_tokens(self) -> int:
        """Every token that entered the model, cached or not."""
        return self.input_tokens + self.cache_write_tokens + self.cache_read_tokens


def _usage_int(usage: Any, name: str) -> int:
    """Read one integer off a usage object, treating absent and None as zero.

    The cache fields are absent entirely on a response that used no caching,
    and present-but-None on some SDK versions. Both mean the same thing, and
    `getattr(usage, name, 0) or 0` collapses them without a branch per field.
    """
    return int(getattr(usage, name, 0) or 0)


def price(usage: Any, model: str) -> Cost:
    """Price one call from its usage object.

    Args:
        usage: anything with input_tokens / output_tokens and, optionally,
            cache_creation_input_tokens / cache_read_input_tokens. The real
            SDK object has all four; a test can pass a SimpleNamespace.
        model: the model id the call was actually made with. Pass
            `result.model`, never a module constant — the point of keying on
            the id is that a model switch cannot be mispriced, and reading the
            constant instead of the result would give that away for nothing.

    Raises:
        UnknownModelError: no entry in PRICING.
    """
    if model not in PRICING:
        raise UnknownModelError(
            f"No pricing entry for model {model!r}. Known models: {sorted(PRICING)}"
        )

    rate_in = PRICING[model]["input"]
    rate_out = PRICING[model]["output"]

    fresh = _usage_int(usage, "input_tokens")
    out = _usage_int(usage, "output_tokens")
    written = _usage_int(usage, "cache_creation_input_tokens")
    read = _usage_int(usage, "cache_read_input_tokens")

    input_usd = fresh * rate_in
    output_usd = out * rate_out
    cache_write_usd = written * rate_in * CACHE_WRITE_MULTIPLIER
    cache_read_usd = read * rate_in * CACHE_READ_MULTIPLIER

    # What the cached tokens would have cost at full input price, minus what
    # they did cost. The write premium is a real extra cost and is subtracted,
    # so the first call of a session shows a small NEGATIVE saving. That is
    # correct and worth seeing: caching only pays from the second call on.
    saved = (read * rate_in - cache_read_usd) - (written * rate_in * (CACHE_WRITE_MULTIPLIER - 1))

    return Cost(
        model=model,
        input_tokens=fresh,
        output_tokens=out,
        cache_write_tokens=written,
        cache_read_tokens=read,
        input_usd=input_usd,
        output_usd=output_usd,
        cache_write_usd=cache_write_usd,
        cache_read_usd=cache_read_usd,
        total_usd=input_usd + output_usd + cache_write_usd + cache_read_usd,
        cache_saved_usd=saved,
    )


def log_call(
    result: Any,
    *,
    latency_s: float | None = None,
    char_count: int | None = None,
    label: str | None = None,
    path: Path | None = None,
    to_stdout: bool | None = None,
) -> dict[str, Any]:
    """Append one line about a call to the call log. Returns the line.

    NOTE THE MISSING PARAMETER. There is no `description`, no `text`, no
    `prompt` and no `output`. This function cannot be made to store what a user
    pasted, or what the model said about it, without editing this file — which
    is the point. `char_count` is there because "the 4,000-character ones cost
    the most" is the operational question you actually have, and it answers it
    without keeping the characters.

    `label` is for YOUR strings only — "day3-smoke", "compare-v012" — never a
    user-supplied one. On Cloud Run pass nothing.

    Args:
        result: a StructuredResult (or anything with .usage, .model, .attempts,
            .stop_reason).
        latency_s: wall-clock seconds for the call, if you timed it.
        char_count: length of the input. NOT the input.
        label: a short caller-chosen tag.
        path: override the log file. Tests must pass tmp_path.
        to_stdout: write the line to stdout instead of a file. Defaults to True
            when running on Cloud Run (K_SERVICE is set), where the filesystem
            is ephemeral and stdout is the log sink.
    """
    cost = price(result.usage, result.model)

    line: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": result.model,
        "attempts": getattr(result, "attempts", None),
        "stop_reason": getattr(result, "stop_reason", None),
        "latency_s": round(latency_s, 3) if latency_s is not None else None,
        "char_count": char_count,
        "label": label,
        **{k: v for k, v in asdict(cost).items() if k != "model"},
    }

    if to_stdout is None:
        to_stdout = bool(os.getenv("K_SERVICE"))

    if to_stdout:
        # print, not logging: stdout on Cloud Run is already structured-log
        # collected, and flush=True because Python buffers stdout when it is a
        # pipe rather than a terminal, which is exactly the case in a container.
        print(json.dumps(line), flush=True)
        return line

    target = path or CALL_LOG_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(line) + "\n")
    return line


# --- Spend cap --------------------------------------------------------------
# A public paste box wired to a personal API key is an unbounded bill with a
# text area in front of it. Nothing in Cloud Run limits what a request costs;
# --max-instances limits how many requests run at once, which is a different
# thing entirely.
#
# This is the cheap version of the guardrail: a running total per process,
# checked before each call. Be honest about what it does NOT do:
#   * it is per instance, so N instances can each spend the cap;
#   * it resets when an instance is recycled, which Cloud Run does freely;
#   * it is not a budget, and it is not a substitute for a billing alert.
# It turns "unbounded" into "roughly cap x max-instances per instance
# lifetime", which for a demo is the difference that matters. Pair it with
# --max-instances on the deploy and a billing alert on the Anthropic account.
DEFAULT_SPEND_CAP_USD = 5.0
SPEND_CAP_USD = float(os.getenv("SPEND_CAP_USD", DEFAULT_SPEND_CAP_USD))

_spent_usd = 0.0


class SpendCapExceeded(RuntimeError):
    """The process has spent its cap. Raised before a call, never after."""

    def __init__(self, spent: float, cap: float) -> None:
        super().__init__(
            f"This instance has spent ${spent:.2f} of its ${cap:.2f} cap. "
            f"The demo is rate-limited by spend rather than by requests; "
            f"try again later, or run it locally with your own key."
        )
        self.spent = spent
        self.cap = cap


def spent_usd() -> float:
    """What this process has spent since it started."""
    return _spent_usd


def record_spend(cost: Cost) -> float:
    """Add one call to the running total. Returns the new total."""
    global _spent_usd
    _spent_usd += cost.total_usd
    return _spent_usd


def check_spend_cap(cap: float | None = None) -> None:
    """Raise if the cap is already spent. Call BEFORE the model call.

    Checking before rather than after means the cap is a ceiling on what has
    been spent when a classification starts, so a sequential caller can
    overshoot it by at most one classification — which is up to `max_attempts`
    billable API calls, not one, because a truncated or invalid reply is
    retried. Concurrent callers can each pass this check before any of them
    records spend; see the notes above on what the cap is and is not.

    A cap of 0 or less disables the check — that is the local-development
    setting, and it is explicit rather than an absent variable.
    """
    cap = SPEND_CAP_USD if cap is None else cap
    if cap > 0 and _spent_usd >= cap:
        raise SpendCapExceeded(_spent_usd, cap)


def reset_spend() -> None:
    """Zero the counter. For tests; there is no reason to call it in the app."""
    global _spent_usd
    _spent_usd = 0.0


def summarise(costs: Iterable[Cost]) -> dict[str, Any]:
    """Total a batch of calls. Used by compare.py and by the UI's session line."""
    costs = list(costs)
    if not costs:
        return {"calls": 0, "total_usd": 0.0}
    return {
        "calls": len(costs),
        "input_tokens": sum(c.input_tokens for c in costs),
        "output_tokens": sum(c.output_tokens for c in costs),
        "cache_write_tokens": sum(c.cache_write_tokens for c in costs),
        "cache_read_tokens": sum(c.cache_read_tokens for c in costs),
        "total_usd": sum(c.total_usd for c in costs),
        "cache_saved_usd": sum(c.cache_saved_usd for c in costs),
        "models": sorted({c.model for c in costs}),
    }


def format_cost(cost: Cost) -> str:
    """One human line, for a CLI or a Streamlit caption."""
    parts = [
        f"{cost.billed_input_tokens:,} in / {cost.output_tokens:,} out",
        f"${cost.total_usd:.4f}",
    ]
    if cost.cache_read_tokens:
        parts.append(f"{cost.cache_read_tokens:,} from cache (saved ${cost.cache_saved_usd:.4f})")
    elif cost.cache_write_tokens:
        parts.append(f"{cost.cache_write_tokens:,} written to cache (first call)")
    return " · ".join(parts)
