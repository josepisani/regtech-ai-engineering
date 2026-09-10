"""compare.py — run the labelled set through the classifier and diff the result.

WHAT IT DOES
    For every row in data/vendor_descriptions.jsonl: classify it, write the
    record plus usage to data/predictions.jsonl, then print where the model
    disagrees with data/labels.jsonl, field by field.

WHY IT EXISTS
    Nothing else in the project measures whether an answer is *right*. The
    schema guarantees shape; only these labels measure correctness. The rows
    printed here are Day 3's edge cases and the Week 3 error-analysis seed.

HOW TO USE IT
    python -m src.aiact.compare            # 20 API calls; writes predictions
    python -m src.aiact.compare --cached   # re-diff the last run, no calls

SCORING RULES
    - Enum and bool fields are compared exactly.
    - legal_basis is compared as a set, and only where the LABEL tier is not
      insufficient_information: those ten rows leave citations blank on
      purpose (review of 2026-09-10) and must not count either way.
    - rationale, gaps and notes are never scored: free text is for humans.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from src.aiact.classify import MODEL, classify_with_meta
from src.aiact.schema import RiskTier

DESCRIPTIONS = Path("data/vendor_descriptions.jsonl")
LABELS = Path("data/labels.jsonl")
PREDICTIONS = Path("data/predictions.jsonl")

# The fields the eval scores, in gate order. Everything else is free text.
SCORED = [
    "act_applies",
    "exclusion_ground",
    "our_role",
    "art25_trigger",
    "risk_tier",
    "annex_iii_derogation",
    "performs_profiling",
    "is_gpai",
    "confidence",
]


def read_jsonl(path: Path) -> dict[str, dict]:
    return {row["id"]: row for row in map(json.loads, path.read_text(encoding="utf-8").splitlines()) if row}


def run() -> None:
    descriptions = read_jsonl(DESCRIPTIONS)
    with PREDICTIONS.open("w", encoding="utf-8", newline="\n") as out:
        for i, (vid, row) in enumerate(descriptions.items(), 1):
            t0 = time.perf_counter()
            record, meta = classify_with_meta(row["text"])
            seconds = time.perf_counter() - t0
            out.write(json.dumps({
                "id": vid,
                "model": meta.model,
                "attempts": meta.attempts,
                "input_tokens": meta.usage.input_tokens,
                "output_tokens": meta.usage.output_tokens,
                "seconds": round(seconds, 2),
                "prediction": record.model_dump(mode="json"),
            }, ensure_ascii=False) + "\n")
            out.flush()  # a crash on row 14 should not lose rows 1-13
            print(f"[{i:2}/{len(descriptions)}] {vid} {record.risk_tier.value:24} "
                  f"{meta.usage.input_tokens}in/{meta.usage.output_tokens}out {seconds:.1f}s",
                  file=sys.stderr)


def diff() -> None:
    labels = read_jsonl(LABELS)
    predictions = read_jsonl(PREDICTIONS)
    misses: dict[str, int] = {f: 0 for f in SCORED + ["legal_basis"]}
    scored_basis = 0

    for vid, label in labels.items():
        pred = predictions[vid]["prediction"]
        rows = [(f, label[f], pred[f]) for f in SCORED if label[f] != pred[f]]
        if label["risk_tier"] != RiskTier.INSUFFICIENT_INFORMATION.value:
            scored_basis += 1
            if set(label["legal_basis"]) != set(pred["legal_basis"]):
                rows.append(("legal_basis", label["legal_basis"], pred["legal_basis"]))
        for f, want, got in rows:
            misses[f] += 1
        if rows:
            print(f"\n{vid}  (label priority {label['priority']}, hesitated={label['hesitated']})")
            for f, want, got in rows:
                print(f"    {f:22} label={want!r:40} model={got!r}")

    n = len(labels)
    print("\nField                    agree")
    for f in SCORED:
        print(f"  {f:22} {n - misses[f]:2}/{n}")
    print(f"  {'legal_basis':22} {scored_basis - misses['legal_basis']:2}/{scored_basis}  (insufficient_information rows excluded)")

    usage = [predictions[v] for v in labels]
    print(f"\n{MODEL}: {sum(u['input_tokens'] for u in usage)} input, "
          f"{sum(u['output_tokens'] for u in usage)} output tokens, "
          f"{sum(u['attempts'] for u in usage)} attempts for {n} rows, "
          f"{sum(u['seconds'] for u in usage):.0f}s")


if __name__ == "__main__":
    if "--cached" not in sys.argv:
        run()
    diff()
