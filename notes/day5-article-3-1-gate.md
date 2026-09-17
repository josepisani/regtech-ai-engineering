# Day 5 — the Article 3(1) gate, and what one eval run is worth

## What started it
A live test on a real vendor page (a portfolio limit-monitoring product; anonymised
as row v021, "LimitWatch") returned a confident `minimal_risk` with three gap questions
about profiling of natural persons — for a tool that never mentions people, and never
says it uses a model. The tier was defensible; the questions were not.

## Diagnosis
The schema has no place for "this is not established as an AI system". So when a
description only lists features (data checks, limits, alerts, reporting), the model
cannot stop at Article 3(1); it walks every later gate, including the profiling gate,
and asks questions about people because the gate exists, not because the text does.
Same defect as the six-error pattern in day3.md. The profiling questions are a
symptom of it.

## The change
One rule added to the prompt (`classify.py`, "Rules for the answer"): if the text does
not state or clearly imply that the system learns, predicts, infers or generates, set
`act_applies` unclear, `risk_tier` insufficient_information, confidence low, and make
the first gap the question whether a machine-learned model is used at all.

## Measured
Baseline (21 rows, incl. v021): tier 14/21, act_applies 12/21, confidence 7/21.
After the rule, two runs, prompt unchanged: tier 16/21 both times, act_applies 15/21,
confidence 12/21 and 11/21.

Stable gains: v003, v004, v021 — wrong before, right in both runs after.
Still wrong in all three runs: v001 (reconciliation engine — named in the rule, still
graded), v007 and v011 (people-scoring texts — the Annex III pull beats the gate).
A prompt rule fixes the feature-list texts, not the people texts.

## What the eval does and does not measure
`compare.py` scores nine enum/bool fields exactly, and legal_basis as a set on the
rows whose label tier is not insufficient_information. It never scores `gaps`,
`rationale` or `notes`: free text is for humans. So the defect that started this
(bad gap questions) is invisible to the score; only the tier and act_applies moved.

## Noise
Between the two identical post-change runs: v019 limited→limited (run 1 had said
minimal), v010 prohibited→high_risk (run 2 only), v002 minimal↔limited. About two rows
in 21 swing between runs with nothing changed. The calls do not set a temperature
(the model's randomness setting), so this is expected; it means any single-run
change of one or two rows is not a finding. "14 to 16" is real because the three
gained rows held in both runs; "16 vs 17" would not be.

v010 changing tier between identical runs is the worst failure this tool can have:
a prohibited-practice case that is sometimes not. Known, logged, not fixed.

## If a Conducting Officer asks "13/20 or 16/21?"
"Sixteen of twenty-one on the tier, plus or minus two rows from run to run, up from
fourteen after one prompt rule. The remaining misses are three texts that describe
decisions about people without saying whether any AI is involved; the model assumes
it is. That needs a schema change, not a better prompt."

## Next
1. Schema: a required `ai_system` field (established / not_established / unclear)
   answered before the tier. Touches schema.py, obligations.py, the tests, the
   labels. Expected to reach v001/v007/v011.
2. `compare.py`: run each row three times, majority-vote the tier, and print the
   rows that disagree with themselves — so the swing is a number, not a feeling.
3. A non-scored diagnostic in compare.py: count gap questions that mention people on
   rows labelled performs_profiling=false. The original symptom, measured.