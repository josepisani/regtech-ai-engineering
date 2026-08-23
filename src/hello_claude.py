"""Smallest useful Claude call: send a prompt, print the reply, and report cost.

Run:  python -m src.hello_claude

This is your Day-1 cost-logger in embryo. Watching real cents-per-call is the
best budget alarm you have, so it's built in from the first script.
"""
from __future__ import annotations

from anthropic import Anthropic

from . import config

# Approximate USD per 1M tokens for Claude Sonnet 5 (input / output).
# These are ballpark figures for a rough cost readout — check the pricing page
# for exact, current numbers: https://www.anthropic.com/pricing
# Note: if you switch CLAUDE_MODEL, update these too or the readout lies.
PRICE_PER_MTOK = {"input": 3.00, "output": 15.00}


def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens / 1_000_000 * PRICE_PER_MTOK["input"]
        + output_tokens / 1_000_000 * PRICE_PER_MTOK["output"]
    )


def main() -> None:
    if not config.ANTHROPIC_API_KEY:
        raise SystemExit(
            "Set ANTHROPIC_API_KEY in your .env first (copy .env.example)."
        )

    client = Anthropic(api_key=config.ANTHROPIC_API_KEY)

    message = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=config.MAX_TOKENS,
        # The word cap is the cheapest lever there is: it cut output tokens ~42%
        # (66 -> 38) versus "one sentence" alone. Output costs 5x input, so
        # bounding the reply beats almost any other tuning on a call this small.
        system=(
            "You are a concise assistant. "
            "Answer in one sentence of at most 20 words."
        ),
        messages=[
            {"role": "user", "content": "In one sentence, what is an AI engineer?"}
        ],
    )

    reply = message.content[0].text
    usage = message.usage
    cost = estimate_cost(usage.input_tokens, usage.output_tokens)

    print("\nReply:", reply)
    print(
        f"\nTokens — in: {usage.input_tokens}  out: {usage.output_tokens}  "
        f"| est. cost: ${cost:.6f}"
    )


if __name__ == "__main__":
    main()
