# EU AI Act System Inventory & Vendor AI Classifier

> Reads an unstructured vendor or system description and returns a validated AI
> Act inventory row: scope, role, risk tier, obligations, legal basis, and the
> questions still to put to the vendor.

**Live demo:** <your Cloud Run URL>
**Stack:** Python 3.11 · Anthropic Claude (Haiku 4.5) · Pydantic · FastAPI · Streamlit · Google Cloud Run

---

## The problem

A Luxembourg management company has to build an inventory of the AI systems it
uses, classify each one under Regulation (EU) 2024/1689, and be able to defend
that classification to a Conducting Officer and eventually to the CSSF. The
input is not a form. It is forty vendor blurbs, procurement notes and intranet
pages that say what a tool is *for* and almost never say what it *does*.

Two good free tools already exist — the Future of Life Institute's compliance
checker, and the European Commission's own on the AI Act Service Desk. **Both
are decision trees for someone who already knows the answers.** You answer the
questions; they apply the logic.

This does the part those cannot: it reads the answers out of the text. Forty
descriptions become forty rows. And where the text does not settle it, it
returns `insufficient_information` **with the questions to ask** — which is
exactly the output a form cannot produce, because a form has already made you
answer them.

## Worked example — nothing to run

**In:**

> TalentFirst AI Screener. Uploads a job posting and a batch of CVs, then
> returns a ranked shortlist with a fit score per candidate. Used by our HR team
> for the first sift on operations roles. SaaS, hosted by the vendor in Ireland.

**Out:**

```json
{
  "system_name": "TalentFirst AI Screener",
  "provider_name": "TalentFirst",
  "system_purpose": "Ranks and scores job applicants' CVs to produce a shortlist for recruiters.",
  "act_applies": "applies",
  "exclusion_ground": "none",
  "our_role": "deployer",
  "effective_role": "deployer",
  "art25_trigger": "none",
  "risk_tier": "high_risk",
  "annex_iii_derogation": "none",
  "performs_profiling": true,
  "is_gpai": false,
  "legal_basis": ["Annex III 4(a)"],
  "obligations": ["Article 26 — deployer of a high-risk AI system: use in accordance with the instructions for use", "..."],
  "gaps": [
    "Does the vendor supply instructions for use and a declaration of conformity?",
    "Are the ranking outputs logged, and for how long?"
  ],
  "rationale": "The system is used for recruitment and specifically to filter applications and evaluate candidates, which is the Annex III point 4(a) use case. We buy and use it under the vendor's name with no modification, so Article 25 does not escalate our role and we remain the deployer. It scores individual candidates, which is profiling of natural persons, so no Article 6(3) derogation could apply even if a limb otherwise fitted.",
  "confidence": "high",
  "classified_at": "2026-09-10",
  "ruleset_version": "v2-2026-09-02-reg-2024-1689-consolidated-20260727",
  "ai_generated": true
}
```

Three things in that record are the whole point:

- **`legal_basis` cites the provision, not a vibe.** Annex III 4(a), and where
  a system is *excluded* it cites the provision relied on to exclude it.
- **`gaps` is a first-class output.** The tool is allowed to say it cannot tell,
  and to say what would settle it.
- **`ruleset_version` pins the law.** The Act moved on 27 July 2026 when the
  Digital Omnibus (Regulation (EU) 2026/1744) came into force. A row without a
  ruleset version cannot be re-checked after the next move.

## Architecture

```
                    ┌─ webapp/ui.py    (Streamlit — the demo)
description ──────► │
                    └─ webapp/main.py  (FastAPI  — POST /classify)
                              │
                              ▼
                 src/aiact/classify.py          the core: knows nothing
                              │                 about HTTP or Streamlit
                              ▼
                 toolkit/structured.py          schema-constrained call,
                              │                 validate + retry, checks
                              ▼                 stop_reason before payload
                    Claude Haiku 4.5
                              │
                              ▼
                 src/aiact/schema.py            Pydantic contract, six gates
                              │
                              ▼
                 src/aiact/obligations.py       Python lookup, NOT generated
```

Four decisions worth defending in an interview:

**Obligations are looked up, never generated.** `obligations.py` is a Python
dict keyed on tier, effective role, GPAI status and the cited provisions. The
model decides *what the system is*; Python decides *what follows from that*.
The model cannot invent an article, and the obligations do not degrade if the
model is swapped for a weaker self-hosted one.

**The gates are answered in order, and each has its own field.** Article 2
scope, Article 3 role, Article 25 escalation, the tier ladder, the Article 6(3)
derogation, and the profiling override. An earlier version asked for one
judgement — the tier — and got the right answer for the wrong reason often
enough to be useless for evals. Six fields mean Day 13 can score each gate
separately instead of reporting one blended accuracy number.

**Validate-and-retry sits on top of grammar-enforced parsing.** Redundant
against Anthropic's structured outputs, and the only guarantee against a plain
self-hosted endpoint — which is the realistic deployment target inside a bank.
The retry feeds the exact validation error back rather than re-rolling the dice.

**Two adapters, one core.** The UI calls the core in-process by default, or
POSTs to the API when `CLASSIFY_API_URL` is set. Same function either way, so
they cannot disagree. It is also the answer to "how would this run inside a
bank": point the UI at an endpoint inside the perimeter, change nothing else.

## Evaluation — measured, not claimed

Ground truth is a hand-labelled set of 20 vendor descriptions
(`data/labels.jsonl`), reviewed against the consolidated Act and the
Commission's own FAQ, with 86 per-cell review comments recorded. **I am the
labeller** — a CFA charterholder and Deputy Head of Risk at a CSSF-regulated
ManCo. Nothing else was going to measure correctness on this.

First run, Haiku 4.5, 20 rows, no retries:

| Gate | Field | Agreement |
|---|---|---|
| Art. 2 scope | `act_applies` | 12/20 |
| — | `exclusion_ground` | 20/20 |
| Art. 3 role | `our_role` | 14/20 |
| Art. 25 escalation | `art25_trigger` | 19/20 |
| **Tier ladder** | **`risk_tier`** | **13/20** |
| Art. 6(3) derogation | `annex_iii_derogation` | 20/20 |
| Profiling override | `performs_profiling` | 20/20 |
| GPAI flag | `is_gpai` | 17/20 |
| Calibration | `confidence` | 8/20 |

**13/20 on the tier is not a good number, and it is the honest one.** The
useful part is that error analysis turned twenty errors into six named
patterns, one of which accounts for six of them: the schema has no field for
Article 3(1), so when the real question is *"is this an AI system at all?"* the
model has nowhere to put that doubt and assesses the risk of a
threshold-matching reconciliation engine instead — confidently. Full analysis
in `notes/day3.md`.

That is what a portfolio project should show: a measured number, a diagnosis,
and a fix with a cost attached — not a demo that works on the five inputs it
was built against.

## What it costs

~7,200 input tokens per classification, of which the description is ~300.
**94% of every call is the same instructions and the same five worked
examples**, so the system prompt is sent as a cached block: written once at a
1.25× premium, then read back at a tenth of the input price.

| | Per call | 20-row eval run |
|---|---|---|
| Without caching | ~$0.0095 | $0.19 (measured) |
| With caching | ~$0.0033 | ~$0.07 (projected) |

The projection is unverified until a real run. `cache_read_input_tokens` in the
usage is the only proof — a cache marker that is too small or misplaced fails
**silently**, at full price, with no error anywhere. Check that field before
believing any figure in this table.

## Run it locally

```bash
git clone <repo-url> && cd ai-eng-starter

uv venv --python 3.11
source .venv/bin/activate          # Windows: .venv\Scripts\activate
uv pip install -r requirements.txt

cp .env.example .env               # then put your ANTHROPIC_API_KEY in it

# the UI
streamlit run webapp/ui.py

# or the API
uvicorn webapp.main:app --reload
curl -s localhost:8000/classify -H 'content-type: application/json' \
  -d '{"description":"TalentFirst AI Screener ranks CVs and scores candidates."}' \
  | python -m json.tool

# or one row on the command line
python -m src.aiact.classify "NavGuard flags anomalous NAV movements overnight."
```

### Tests

```bash
pytest                 # 29 offline tests: no key, no network, no money
pytest -m live         # 4 tests that call the real model; needs a key
```

The offline suite covers the input guards, the truncation and refusal paths,
the pricing arithmetic, and the Act gates decided in Python — including that
the Annex III 5(b) fraud carve-out produces **no** Article 6(4) duty while an
Article 6(3) derogation **does**. Those two are the classification this tool is
most likely to get wrong, and they now cost nothing to check on every commit.

## Deploy to Cloud Run

One image, two services, selected by `APP_MODE`.

```bash
gcloud config set project $GOOGLE_CLOUD_PROJECT
gcloud services enable run.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com

# the API key goes in Secret Manager, never in the image and never in an env var
echo -n "$ANTHROPIC_API_KEY" | gcloud secrets create anthropic-api-key --data-file=-

# the public demo (Streamlit)
gcloud run deploy aiact-classifier \
  --source . --region europe-west1 --allow-unauthenticated \
  --set-secrets ANTHROPIC_API_KEY=anthropic-api-key:latest \
  --set-env-vars APP_MODE=ui,SPEND_CAP_USD=5 \
  --max-instances 2 --session-affinity --timeout 300

# the JSON endpoint, same image
gcloud run deploy aiact-api \
  --source . --region europe-west1 --allow-unauthenticated \
  --set-secrets ANTHROPIC_API_KEY=anthropic-api-key:latest \
  --set-env-vars APP_MODE=api,SPEND_CAP_USD=5 \
  --max-instances 2
```

```bash
# shorten log retention. Cloud Run request logs carry the caller's IP address,
# which is personal data whether or not anyone types any. The _Default bucket
# keeps 30 days; a demo needs days, not weeks.
gcloud logging buckets update _Default --location=global --retention-days=7
```

`--session-affinity` is not optional for the Streamlit service: Streamlit holds
a websocket per user, and without affinity a second instance can pick up a
reconnect and lose the session. `--max-instances 2` caps how many copies of the
spend cap can exist at once.

`SPEND_CAP_USD` is the guardrail that matters most on a public demo: a paste box
wired to a personal API key is an unbounded bill with a text area in front of
it, and nothing in Cloud Run limits what a request costs. The cap is per
instance and resets when an instance recycles, so it is a blast-radius limit,
not a budget — pair it with a billing alert on the Anthropic account.

**Map a custom domain.** A `*.run.app` hostname is the single most-filtered
shape there is on a corporate network — see below.

## Two things that are true about this demo

**A hosted demo is not usable inside a ManCo.** Luxembourg banks and financial
entities run URL filtering and DLP; a `*.run.app` URL is likely unreachable
from inside one, and where it is reachable the DLP may block the paste. Hiring
managers open it on a phone, which is what it is for. A real deployment target
is the firm's own internally-managed open-weight model behind its own
perimeter, which is why obligations come from Python and why the wrapper
validates and retries.

**Publishing it makes me its provider.** `putting into service` is the supply of
an AI system for first use to a deployer *or for own use*, with no commercial
qualifier. The tool itself is limited-risk — it classifies systems, not people —
so nothing in Chapter III applies. What does apply is Article 50(1) (say it is
AI), Article 50(2) (mark the output as generated — hence `ai_generated` in every
record), and Article 4 (AI literacy). Checklist in
`notes/day4-publishing-checklist.md`.

## Data handling

**Nothing entered is stored.** The description is sent to the model to be
classified and then discarded. Rows live in the browser session's memory and go
when the tab closes. The cost log records how long a description was, never
what it said — `toolkit/costlog.log_call` has no parameter that could take the
text, and a test asserts that it does not grow one. Error responses describe
the failure without repeating what was sent, which took a fix: the first
version echoed an over-long paste straight back in the 422 body. Unexpected
errors log the exception *type* only, not a traceback, because a traceback can
carry the request that caused it.

Not storing is not the same as not processing, and processing is what GDPR
turns on. Operating this demo publicly makes me the **controller** and Anthropic
the **processor**, running the model in the United States under its commercial
terms. Two consequences that are handled rather than hoped away:

- **The interface refuses the data rather than protecting it.** Four worked
  examples are the default path; free text is a deliberate second choice behind
  a notice. Most visitors want to see what the tool does, which an example
  answers. Not receiving personal data beats holding it safely.
- **Access logs carry IP addresses**, independently of anything anyone types.
  Retention is shortened at deploy time (below) rather than left at the default.

The examples are chosen inputs the model has never seen — none is a few-shot
example from the prompt. Demoing a model on its own worked examples is a rigged
demo, and it takes about a minute to catch.

## AI literacy (Article 4)

This tool uses a large language model to read the description. It is wrong
about 1 tier in 3 on the current test set, and it is wrong in patterns worth
knowing: it under-uses `insufficient_information`, and it drifts toward
`high_risk` around financial-services language, because that language is full
of risk, regulation and client money while Annex III is a specific list of uses
mostly concerning decisions about people. Every row is a first draft for a
human reviewer. Read the rationale before accepting the tier.

## Disclaimer

Results are **informational only**. This is **not legal advice** — consult a
qualified professional. It is **not an official or authoritative assessment** of
your situation, and it neither creates nor discharges any obligation under
Regulation (EU) 2024/1689.

---

Built as part of a 20-day AI-engineering sprint. The through-line: *I automate
the regulatory work I spent eight years doing by hand.*
