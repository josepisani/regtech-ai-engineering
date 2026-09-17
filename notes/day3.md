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

> Superseded on Day 5: 16/21 on the tier and 15/21 on act_applies after the
> Article 3(1) prompt rule, on 21 rows. The table above is the Day 3 record and
> stays as measured. See `day5-article-3-1-gate.md`.

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

## Day 3 build — 2026-09-10

Everything below is the Day 3 "Done when" bar from START-HERE §4, and nothing
beyond it. The six accuracy patterns above are untouched: five of them (B-F)
are prompt tuning and belong to Day 13's error analysis, and pattern A is a
schema change that needs a decision before it is written (see "Open decision").

### What landed

**`toolkit/costlog.py` (new, the Day 3 toolkit promotion).** `price()`,
`log_call()`, `summarise()`, `format_cost()`. Pricing now lives in exactly one
place; `llm_probe.py` keeps its own copy on purpose as the standalone teaching
file, nothing else should. Prices the two cache buckets as multiples of the
input rate (write 1.25x, read 0.10x) rather than as typed-in figures.

`log_call` has **no parameter that can take the description** - not `text`, not
`prompt`, not `output`. `char_count` is offered instead. That is the no-logging
decision built in on Day 3 rather than removed on Day 4, and there is a test
asserting the signature so it cannot be added back "just for debugging".

**Prompt caching.** `toolkit/structured.cached_system()` builds the system
prompt as content blocks with an `ephemeral` cache breakpoint on the last one;
`classify.SYSTEM_BLOCKS` is built once at import. The description stays in the
user message, because anything before the breakpoint changes the cached prefix
and misses on every row.

Expected effect on the numbers measured above: ~6,900 of the ~7,200 input
tokens per call become cache reads at 0.10x. Input cost per call falls from
~$0.0072 to ~$0.0010, and the 20-row comparison from **$0.19 to roughly $0.07**.
Unverified until a real run - `cache_read_input_tokens` in the usage is the
only proof, and a cache marker that is too small or misplaced fails **silently**
at full price. Check that field before quoting any saving.

**Input guards.** `validate_description()` in the core, called by both the API
and the UI so they cannot drift. Empty -> `ValueError`. Over
`MAX_DESCRIPTION_CHARS` (8,000, ~4x the longest labelled description) ->
`DescriptionTooLongError`. Both raise before a socket opens.

**`webapp/main.py` - `POST /classify`.** A thin adapter over `classify_with_meta`.
422 where the caller must change what they sent (empty, too long, refusal),
502 where the model was reached but produced nothing usable. Response carries
`ai_generated: true` as a field, so the Article 50(2) marking survives export
to CSV and into whatever register the row ends up in.

**`webapp/ui.py` - Streamlit.** Paste box, tier badge, obligations, gaps, legal
basis, rationale, and a session table with CSV/JSON download - forty
descriptions becoming forty rows is the differentiator, so the table is the
demo. Article 25 escalation is surfaced as a banner only when stated and
effective role differ. Sidebar carries the data-handling statement, the AI
literacy line (Art. 4) and the prior-art comparison; the Art. 50(1) "you are
interacting with an AI system" notice sits above the input; the disclaimer is
at the foot.

`CLASSIFY_API_URL` unset -> the UI imports the core and calls it in-process.
Set -> it POSTs to that endpoint instead. Same core either way, so the two
adapters cannot disagree about a classification, and "how would this run inside
a bank?" has a one-variable answer.

**`tests/` - 29 offline tests, 4 live.** `conftest.py` carries a `FakeClient`
that replays scripted responses, so truncation, refusal and retry paths are
tested with no key, no network and no money. Live tests (gibberish, a non-AI
vendor, the fraud carve-out, the profiling override) are marked `live` and
skipped unless `pytest -m live` is asked for AND a key is set.

The Act gates that Python decides are now offline regression tests: the
Annex III 5(b) carve-out produces **no** Article 6(4) duty, an Article 6(3)
derogation **does**, and Article 25 escalates only on the high-risk path. Those
run on every commit and cost nothing.

### One real defect, found by a test rather than by reading

The request model first used Pydantic's `max_length=`. Pydantic puts the
offending value in the error's `input` field and FastAPI serialises the whole
error list into the 422 body - so an over-long paste **came straight back to
the caller**, all 9,000 characters of it, and would have reached anything
watching 4xx responses.

Fixed two ways: the length rule moved to `validate_description` (where the UI
hits it too), and a `RequestValidationError` handler now strips `input` and
`ctx` from every validation error. `test_no_api_error_response_repeats_what_was_pasted`
checks four different bad requests, because the leak was not a property of the
length rule - it was a property of returning error objects built by someone else.

This is rule 6 from START-HERE §2 again: the wrong answer came from our own
Python, not from the model. It is also the answer to "what did you find in
testing?" in an interview.

### Verified

Offline suite 29 passed / 4 skipped. FastAPI checked end-to-end with a stubbed
core: 200 on the happy path, 422 on empty/over-long/refusal, 502 on retry
exhaustion and on an upstream 401, and no error body repeats the input. The
Streamlit page was executed with `streamlit.testing.v1.AppTest` against a live
local FastAPI instance: renders the row, the escalation banner, the session
table, both downloads and the cost line. With no API key it shows a clean
error under the button instead of a stack trace - the Day 3 "does not crash on
bad input" bar.

Not verified, and cannot be from here: a real API call. **Run the live tests
and one real classification yourself before calling Day 3 closed**, and confirm
`cache_read_input_tokens` is non-zero on the second call.

### Line endings

The repo is mixed: `.py`, `requirements.txt`, `.gitignore` and `CLAUDE.md` are
CRLF; `notes/*.md` are LF. Everything written today was normalised to match its
neighbours before being written back, and `requirements.txt` was checked
byte-identical for its first 153 bytes so the append could not have touched the
existing eight lines.

The root fix is still `.gitattributes`, listed above as deliberately not done.
It stays not done: adding it renormalises the whole repo in one commit, which
is a change worth making on its own rather than buried in a feature day.

### Open decision, before Day 4 deploys anything

Pattern A - the Article 3(1) gate, six of twenty rows, the biggest single loss.
The schema has nowhere to put "this may not be an AI system at all", so the
model assesses the *risk* of a threshold-matching reconciliation engine and
returns a tier with `high` confidence.

Deploying publicly without it means a tool that tells a bank its reconciliation
engine is high-risk AI, confidently. That is the professional-liability problem
the Day 4 disclaimer exists for, and a disclaimer is a weaker fix than a gate.

Proposed shape, for a decision rather than a build:
  - new field `is_ai_system`: `ai_system` | `not_an_ai_system` | `unclear`,
    answered as Gate 0, before Article 2;
  - `unclear` -> `risk_tier` = `insufficient_information` with a gap question
    ("does it infer outputs from inputs, or apply fixed rules a person wrote?"),
    which is exactly what the six labels say;
  - `not_an_ai_system` -> `act_applies` = `excluded` with a new
    `exclusion_ground`, so `obligations_for` returns nothing without new logic;
  - one prompt gate and one worked example; the labels do not change.

Cost to test: one re-run of `compare.py`, ~$0.07 with caching on.

## Privacy changes, same day — after the question "can I see what testers paste?"

The honest answer was no, and that was the wrong test. Not storing is not the
same as not processing, and processing is what GDPR turns on: operating this
publicly makes the operator the controller and Anthropic the processor, and the
Cloud Run access log carries the caller's IP whether or not anyone types
anything sensitive.

Five changes, all cheap, none of them legal advice:

1. **`logger.exception` -> `logger.error` with the exception type only.** The
   traceback could carry the request that caused it - an SDK error for a
   malformed request may quote the body it sent, and that body is the
   description. Low probability, and exactly the leak the page says does not
   happen. The cost is real: a 502 is now harder to debug from the log alone.
   Reproduce it locally with your own description instead, where a full
   traceback is free.

2. **`webapp/examples.py` (new), and the demo leads with it.** Four worked
   examples in a picker; free text is a second radio option. The ordering IS
   the control: most visitors want to see what the tool does, which an example
   answers, so the people who type are a much smaller group who have read a
   notice first. Capability unchanged, default changed.

3. **A notice beside the text box, not in a policy page.** Do not paste
   personal data or client information; what you enter goes to Anthropic's API
   in the United States, is classified and discarded, is not stored here and
   cannot be retrieved by the operator. That is Article 13 in the place it is
   actually read.

4. **The sidebar names controller and processor**, says the access log holds IP
   addresses, and points at the examples as the reason free text is not needed.

5. **Log retention shortened at deploy** - `gcloud logging buckets update
   _Default --retention-days=7`, in the README deploy block. Thirty days of IP
   addresses for a portfolio demo is a default, not a decision.

### On the examples

None of the four is a few-shot example from the prompt. Demoing a model on its
own worked examples is a rigged demo and takes an interviewer about a minute to
catch. They are chosen so each interesting outcome appears once: ShortlistPro
(high_risk, Annex III 4(a)), FraudLens (NOT high_risk - the 5(b) fraud
carve-out, the most counter-intuitive answer the tool gives), Aurora
(insufficient_information with the questions to ask - the output a decision
tree cannot produce), ClientDesk (limited_risk, Article 50).

A fifth belongs there and is deliberately held back: a deterministic
threshold-matching reconciliation engine, where the real question is Article
3(1), "is this an AI system at all?". The schema has no field for it yet
(pattern A above), so the tool answers confidently and wrongly. It becomes the
best example in the set the day that gate lands.

### Still open

The Anthropic DPA and the transfer terms covering that processing. That is a
document to accept and file, not code - and it is a precondition for the public
deploy, not a Day 5 tidy-up.

## Caching verified — 2026-09-10, evening

Ran the UI against the real API. One classification of the FraudLens example:

    claude-haiku-4-5 · 8.593s · attempts 1 · $0.0030
    7,138 input tokens from cache, saving $0.0064

So the projection above was slightly pessimistic. Measured, per call:

| | Per call | 20 rows |
|---|---|---|
| Uncached (mean of the 20-row run) | $0.0095 | $0.19 |
| Cached | $0.0030 | ~$0.060 |

**−68%.** The 20-row cached figure is the per-call cost multiplied out, not a
second full run. README says so too rather than implying otherwise.

`cache_read_input_tokens` was non-zero, which is the only thing that proves the
breakpoint is real. Worth repeating because it is the trap: a marker that is too
small, or placed after something that varies per call, is accepted and then
ignored — no error, normal response, full price on every row.

**Watch, do not act:** 8.593s against the Day 2 median of 4.1s. One sample, most
likely first-call warm-up, and cache reads should be faster rather than slower.
If it holds near 8s across a batch it needs looking at before any latency figure
goes in the README. Nothing in the README quotes a latency yet, deliberately.

## Day 3 closed

The "Done when" bar from START-HERE §4 was: runs end-to-end locally and does not
crash on bad input. Met. Empty, over-long, missing key, upstream failure and
refusal all produce a message rather than a stack trace, and the offline suite
covers each.

One defect found after committing: `streamlit run webapp/ui.py` puts the
script's own folder on `sys.path`, not the folder the command was run from, so
`webapp`, `src` and `toolkit` were all invisible and the page failed with
ModuleNotFoundError before rendering. The test harness ran the page as an
ordinary Python process from the repo root, where the repo root is already on
the path, so it could not reproduce the failure. Day 1 rule 2 again: a test that
cannot fail teaches nothing. Fixed by putting the repo root on the path at the
top of the file, and verified by reproducing Streamlit's path setup rather than
by running the tests again.
