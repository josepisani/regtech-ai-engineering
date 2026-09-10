# Day 3 — 2026-09-10

Branch `day3`. Day 3 "Done when" not yet read from START-HERE; nothing below
claims Day 3 complete. This is the Day 2 handoff list finished, plus the first
measurement of correctness.

## Done

1. `data/labels.jsonl` is the ground truth (commit `ac28d88`). Reviewed
   workbook of 2026-09-10: v009 exclusion corrected, four unsupported
   Art. 6(3) derogations cleared, GPAI set on v012/v019/v020, Art. 50 tiers
   checked against the Commission FAQ. The 86 per-cell review comments ride
   along in `review_comments`. Workbook untracked and git-ignored.
2. Few-shot example 5 (`InterviewScribe`) amended (commit `241d6f2`): the
   Art. 6(3)(d) conditions are stated as facts in the description, Art. 50 is
   assessed separately before `minimal_risk`, the GPAI statement is in the text
   rather than invented. Example 1 stays as the contrast (ranking = profiling).
3. `src/aiact/compare.py`: runs the 20 descriptions, writes
   `data/predictions.jsonl` with usage, diffs against the labels. `legal_basis`
   scored only where the label tier is not `insufficient_information` (ten
   rows, blank citations by design).

## First run — `claude-haiku-4-5`, 20 rows, 20 attempts (no retries)

| Field | Agree |
|---|---|
| act_applies | 12/20 |
| exclusion_ground | 20/20 |
| our_role | 14/20 |
| art25_trigger | 19/20 |
| **risk_tier** | **13/20** |
| annex_iii_derogation | 20/20 (never fired on either side) |
| performs_profiling | 20/20 |
| is_gpai | 17/20 |
| confidence | 8/20 |
| legal_basis | 5/10 scored |

145,260 input / 9,395 output tokens, 200 s. **$0.19** at the Day 1 prices
($1 / $5 per MTok). ~7.2k input per call of which the description is ~300:
**94% of input is the fixed system prompt and examples** — that is the prompt
caching target.

## What the disagreements are — six patterns, not twenty errors

**A. It never says "insufficient" when the question is "is this AI at all?"
(6 rows, the biggest loss).** v001, v003, v004 → `minimal_risk`; v002 →
`limited_risk`; v007, v011 → `high_risk`; all labelled
`insufficient_information`, five at model confidence `high`. The v001
rationale shows the mechanism: it assesses the *risk* of a threshold-matching
reconciliation engine without ever asking whether it is an AI system. The
schema has no field for Art. 3(1), so the model has nowhere to put "this may
be ordinary software" and defaults to `applies` + a tier. This is the Art. 3(1)
gate already recorded as an intended Day 3 change — now with six rows of
evidence. Not built yet: waiting on the Day 3 criteria.

**B. `provider` where we bought it (v012, v014, v019; v011 too).** The
rationales say "deployed in-house", "built on proprietary LLM", "fine-tunes a
foundation model" → provider. The descriptions are genuinely ambiguous —
the v019 label's own gap asks who does the fine-tuning — and the model
resolves the ambiguity toward provider while the labels resolve it toward
deployer. Candidate prompt rule: "in-house deployment" and "proprietary" do
not make us the provider; provider only where the description says we
developed it or place it on the market under our name; otherwise `unclear`.
Labels stay as they are.

**C. v010 — ladder violation, priority 1.** Cites Art. 5(1)(f), rationale says
"explicitly prohibited", then picks `high_risk` on Annex III 4(b). The prompt
says stop at the first rung; the model kept walking. Probable cause: **none
of the five few-shot examples is `prohibited`** — the top rung has no worked
example. Cheapest fix to test first: a sixth example, or one explicit line
"any Art. 5 hit is `prohibited`, whatever else also applies".

**D. Confidence is not calibrated (8/20).** `high` on 15 rows. The schema
defines `low` as "material facts are missing"; the model does not apply its
own definition, and cannot while pattern A hides the missing facts from it.
Expect D to move when A is fixed; do not tune it separately first.

**E. Art. 50 sub-paragraph.** 50(1) where the label says 50(2) on v013 and
v019 — the v019 rationale conflates "staff use it through a portal" (not
50(1), which is interaction with a natural person as such) with "generates
synthetic text" (50(2)). v005 cites nothing. v012 is `50(1)(b)` vs `50(1)` —
a granularity mismatch the scorer should normalise, not an error. The prompt
has no Art. 50 guidance beyond the tier line; the Commission FAQ the labels
were checked against is the source to write it from.

**F. `is_gpai` is a definition, not an error (v002, v005, v013).** The model
infers a GPAI model from "proprietary summarisation" or a code plugin; the
labels set it only where the description names an LLM or foundation model
(v020 review comment). Decide which rule, write it into the field
description, then score it.

**Untested:** the derogation gate never fired on any row — no description
exercises Art. 6(3)(d). The InterviewScribe amendment is therefore neither
confirmed nor contradicted by this set. Needs a synthetic row that is a
genuine preparatory task, and one that only looks like one.

## Not done, on purpose

Art. 3(1) gate, prompt caching, `.gitattributes`, UI — all pending the Day 3
"Done when" line from START-HERE. `openpyxl` was installed into the venv for
the one-off conversion and is not in `requirements.txt`; the scratch script is
gone.
