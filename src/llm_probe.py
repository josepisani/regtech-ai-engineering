"""llm_probe.py — streaming probe for Claude API calls.

Calls Claude, streams the response, and reports input/output tokens,
time-to-first-token, total latency and real $ cost per call. Prices are in the
PRICING table below, keyed by model id so a model switch cannot be mispriced.

Usage: py -m src.llm_probe "your prompt"      (also: py src/llm_probe.py "...")

Note on temperature: sent only for models in TEMPERATURE_MODELS. anthropic 1.x
removed sampling parameters from the typed method signature altogether, because
Opus 5, Sonnet 5 and Fable 5 reject them — so passing temperature= as a keyword
is a local TypeError, not a 400. Of the models priced below, only Haiku 4.5
still accepts one; for the rest it is warned about and dropped, not sent.
"""
from __future__ import annotations

import os
import sys
import time
import warnings

from anthropic import Anthropic
from dotenv import load_dotenv

# --- Config -----------------------------------------------------------------
# .env is loaded inline rather than through src.config so this file stays
# copy-pasteable into toolkit/ or another project with no repo dependency.
load_dotenv()

MODEL = "claude-haiku-4-5"

# USD per *token*. The published $/1M figure is left visible in the arithmetic
# so it can be checked against the pricing page without decoding a float.
# Keyed by model id: a flat input/output pair cannot notice a model switch and
# would price the wrong model in silence.
PRICING = {
    "claude-fable-5":   {"input": 10.00 / 1_000_000, "output": 50.00 / 1_000_000},
    "claude-opus-5":    {"input":  5.00 / 1_000_000, "output": 25.00 / 1_000_000},
    "claude-sonnet-5":  {"input":  2.00 / 1_000_000, "output": 10.00 / 1_000_000},
    "claude-haiku-4-5": {"input":  1.00 / 1_000_000, "output":  5.00 / 1_000_000},
}

# Models that still accept sampling parameters. Sampling was removed from the
# 5-series and the 4.7/4.8 Opus line — sending `temperature` to those returns a
# 400. The rule for maintaining this set: a model belongs here only if the
# pricing/API docs still list temperature as a valid parameter for it.
TEMPERATURE_MODELS = {
    "claude-haiku-4-5",
    "claude-haiku-4-5-20251001",
    "claude-sonnet-4-6",
    "claude-opus-4-6",
    "claude-sonnet-4-5",
    "claude-opus-4-5",
}

# Fail at import, before a prompt is read or a socket is opened. A bad model id
# announces itself as a 404 on the first request; a MODEL/PRICING mismatch never
# announces itself at all — so the guard goes where there is no natural alarm.
# `raise`, not `assert`: asserts are stripped under `python -O`.
if MODEL not in PRICING:
    raise RuntimeError(
        f"No pricing entry for MODEL={MODEL!r}. Known models: {sorted(PRICING)}"
    )


def probe(
    prompt: str,
    system: str | None = None,
    temperature: float | None = None,
    max_tokens: int = 512,
) -> dict:
    """Stream one completion, print it as it arrives, then report the metrics.

    `temperature=None` means "don't send one" — the API applies its own default
    of 1.0. Passing a number on a model that no longer accepts sampling params
    warns and drops it rather than letting the request 400.
    """
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise SystemExit("Set ANTHROPIC_API_KEY in your .env first.")

    client = Anthropic()  # picks the key up from the environment load_dotenv filled

    # --- Request assembly -------------------------------------------------
    # Built as a dict so an unsupported parameter can be left out of the request
    # entirely. A key that is never added is unambiguously absent — no None to
    # serialize as null, and no duplicated call sites for each combination.
    params = {
        "model": MODEL,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    # Empty string counts as "no system prompt" — an empty one is meaningless.
    if system:
        params["system"] = system

    # Only reached when the caller actually asked for a temperature, so the
    # warning fires on a real mistake instead of on every call to a 5-series
    # model. anthropic 1.x dropped sampling params from the typed method
    # signature, so it travels through extra_body, the SDK's documented hatch.
    if temperature is not None:
        if MODEL in TEMPERATURE_MODELS:
            params["extra_body"] = {"temperature": temperature}
        else:
            warnings.warn(
                f"{MODEL} does not accept temperature; dropping temperature="
                f"{temperature} to avoid a 400. Use a model in "
                f"TEMPERATURE_MODELS if you need sampling control.",
                stacklevel=2,
            )

    # --- The call ---------------------------------------------------------
    # perf_counter is monotonic (time.time can jump backwards on an NTP fix).
    # t0 sits before the `with` so connection setup and request serialization
    # count too — that is time the user spends waiting.
    t0 = time.perf_counter()
    first_at: float | None = None
    chunks: list[str] = []

    with client.messages.stream(**params) as stream:
        for text in stream.text_stream:
            if first_at is None:  # `is None`, so a legitimate 0.0 can't re-fire it
                first_at = time.perf_counter()
            chunks.append(text)
            print(text, end="", flush=True)  # without flush this batches when piped

        # Usage exists only once the stream has drained: output tokens arrive in
        # the final message_delta event, not up front.
        message = stream.get_final_message()

    # Total is measured after get_final_message() — the message is not done
    # until its last event has been read.
    latency = time.perf_counter() - t0
    # No text at all (an empty or tool-only response) means there was no first
    # token; fall back to total rather than reporting a fake zero.
    ttft = (first_at - t0) if first_at is not None else latency

    # --- Metrics ----------------------------------------------------------
    usage = message.usage
    price = PRICING[MODEL]
    cost = usage.input_tokens * price["input"] + usage.output_tokens * price["output"]

    result = {
        "model": MODEL,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "ttft_s": round(ttft, 3),
        "latency_s": round(latency, 3),
        "cost_usd": cost,
        "text": "".join(chunks),
    }

    # --- Readout ----------------------------------------------------------
    print(
        f"\n\ntokens — in: {result['input_tokens']}  out: {result['output_tokens']}"
        f"\nttft:  {result['ttft_s']:.3f}s   total: {result['latency_s']:.3f}s"
        f"\ncost:  ${cost:.6f}   ({MODEL})"
    )
    return result


def main() -> None:
    # Join argv instead of taking argv[1]: an unquoted prompt arrives as many
    # separate words, and silently probing only the first one is a bad surprise.
    prompt = " ".join(sys.argv[1:]).strip()
    if not prompt:
        raise SystemExit('Usage: py -m src.llm_probe "your prompt here"')
    probe(prompt)


if __name__ == "__main__":
    main()
