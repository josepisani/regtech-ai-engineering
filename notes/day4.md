# Day 4 — 2026-09-15

## Decision: no public paste box

START-HERE Day 4 says deploy to Cloud Run, custom domain, public demo. Changed
today: the only thing that goes public is a **static showcase** — figures,
worked examples, the accuracy table — on GitHub. Nobody but me runs the model.
Live demos are in person, from a local run.

Why. A public paste box is the largest real risk in the publishing checklist
(strangers paste CVs; I become a GDPR controller), and it buys nothing a
figure cannot show. The audience — Conducting Officers, hiring managers — wants
to see what it does and what it gets wrong, not to type into it. A `*.run.app`
URL is unreachable from most ManCo desks anyway. The Dockerfile and deploy
commands stay in the repo as evidence of the skill; they are not the product.

What that removes from the checklist: Art. 50(1) "you are interacting with AI"
(nobody interacts), the GDPR paste risk (gone by construction), the custom
domain (moot). What stays: `ai_generated` on every displayed record, the
disclaimer, the AI-literacy line — and the disclaimer gains weight, because a
page that shows classifications is still telling readers what obligations
look like.

START-HERE needs updating to say this. Done here first so the reasoning is on
record.

## Showcase inputs — five calls, ~$0.02

Ran the four `webapp/examples.py` inputs and the tool's own description
through the CLI; records in `data/showcase/`. All four in one attempt, all
reading the cached prefix. The four tiers came back as the four *different*
answers the tool can give — high_risk, minimal_risk, insufficient_information,
limited_risk — which is what a showcase needs, and the AML case stayed
minimal_risk (the Day 3 drift toward high_risk around financial language did
not recur on this input).

Windows lesson on the way: a Python child process writes stdout in cp1252,
not UTF-8, so the `·` and `—` in the cost line broke a UTF-8 reader. One call
wasted. `PYTHONUTF8=1` in the child's environment fixes it; the Linux
container never sees this, which is why it surfaced here and not in tests.

Latency: 6–10 s per call at ~7.2k input tokens, consistently. The 8.6 s from
Day 3 was not a warm-up outlier. Not investigated; not a Day 4 problem.

## The tool on its own description

First run, badly framed ("built and operated by an individual" — from a
ManCo's "our role" seat, that is a third party): `our_role: unclear`,
`minimal_risk`. My framing, not the tool's fault. Re-run in the first person
("we built this and operate it under our own name, free of charge"):
`provider` / `limited_risk` / Art. 50(2) / confidence high. Correct.

One defect survives both runs. The model reaches limited_risk through
Art. 50(2) (it generates text) but rules *out* 50(1) with an invented
qualifier — "does not interact directly with natural persons *in a manner
that materially affects them*". Art. 50(1) has no such threshold. The phrase
almost certainly leaks from the InterviewScribe few-shot, whose Art. 6(3)
argument uses "materially influence". Right tier, one wrong leg of reasoning.
A ruleset change, so it needs the 20-row eval re-run to check for regression
— Day 5 territory, not today. Logged, not fixed.

## External code review — two findings, both real

The reviewer was a second model — ChatGPT, GPT 5.6 SOL — given the brief in
`notes/day4-code-review-brief.md` and read access to the repo; the code was
written with Claude, so this is one model checking another's work, the same
second-opinion pattern as `notes/gemini-second-opinion-runbook.md`. It worked
in the working tree (not a `review/` branch as asked). What it found:

**1. The retry loop was unreachable in production.** `call_schema` used
`messages.parse()`, which validates the reply *inside the SDK* and raises
`ValidationError` on a truncated reply — before the `stop_reason == "max_tokens"`
check could run. The truncation and validation-retry tests passed only because
the fake client had a `parsed_output` field that handed over an
already-validated object at a point where the real SDK would already have
raised. Same family as Day 3's "a test that cannot fail teaches nothing";
this one is "a fake that bypasses the boundary proves nothing."

Fix: `messages.create()` with an explicit `output_config` (built with the
SDK's own `transform_schema`), returning the message raw; validation done
locally with `schema.model_validate_json`. The fake now has both methods and
its `parse()` validates like the real one, plus a test that guards the fake
itself, plus one test that goes through a real `Anthropic` client over a
mocked transport to prove `output_config` is accepted as built.

**2. Two error-message leaks.** The API's 502 returned `SchemaRetryError.last_error`
— Pydantic's text, which quotes the rejected value, and the rejected value can
be a field the model filled from the description. The Streamlit page showed
`str(exc)` for every exception, including SDK errors that can quote the
request. Proved with a sentinel that came straight back in the body. My
comment in `main.py` had argued the validation error "is about our schema,
not the caller's text" — plausible and wrong.

Fix: `webapp/errors.py`, one function that maps every failure to a fixed
sentence *by exception type*; only two exception classes written by this
codebase pass their text through. Both adapters use it. A sentinel test per
adapter now asserts nothing pasted ever comes back. The CLI is the one place
`last_error` is still shown, because there the text is your own.

**Consequences it followed through:** failed attempts are now billed
(`Usage` summed over every reply; `StructuredError` carries it; both adapters
charge the cap before the error leaves — before this, a stream of failing
requests ran against my key while the cap read zero). And the wording "rows
live in the browser session's memory" was false: `st.session_state` is
server-side. Corrected in three places to "held transiently in server-side
session memory, not written to disk or a database." Less reassuring, and true.

33 → 41 tests. One live classification through the new path: record returned,
`attempts=1`, same tier as the morning run.

Open from the review, not yet acted on: the real-SDK test imports `httpx2`
(the SDK's vendored httpx); if a release renames it the test fails with an
`ImportError` rather than a clear skip.

## Still to do on Day 4

- Export the eight showcase figures to `docs/figures/`; rewrite the README
  around them (showcase link, "live demo on request", a "What a Conducting
  Officer will ask" section).
- `toolkit/deploy/` — the Dockerfile stays at the root (gcloud only finds it
  there); the deploy script and a note go in the toolkit.
- Tick the checklist; update START-HERE.
