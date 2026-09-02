# Runbook — decorrelated second-opinion review on Gemini (Vertex AI)

*2026-09-02. Purpose: have a model from a **different provider** attack the legal
layer of Project 1, on the GCP credit that expires 2026-11-17.*

**Why a different provider and not a bigger Claude:** the value of a second
review is *decorrelation*, not intelligence. Another Claude shares training data,
priors and failure modes with the first — it agrees with it, including where it
is wrong. This exercise is only worth running if the reviewer is genuinely
independent.

**Why it is not the same as "ask Gemini what it thinks":** the reviewer gets the
**primary source** (the consolidated AI Act) and is told to cite it. A finding
without an article quote is discarded. Model opinion is not evidence.

---

## Step 0 — Decide the route

| | Gemini Developer API | **Vertex AI (use this)** |
|---|---|---|
| Auth | API key | Application Default Credentials |
| Billing | Google account | **the GCP project — burns the €263 credit** |
| Setup | 1 minute | ~5 minutes |

The credit expires **2026-11-17** and is otherwise wasted. Use Vertex.

## Step 1 — Enable the API and authenticate

```bash
gcloud config set project gen-lang-client-0987507894
gcloud services enable aiplatform.googleapis.com
gcloud auth application-default login
```

The last command opens a browser and writes Application Default Credentials to
your user profile. It is a login, not a key file — nothing to commit, nothing to
leak.

## Step 2 — Install the SDK

```bash
uv pip install google-genai
```

## Step 3 — Environment

Add to `.env` (git-ignored, recreated per machine — never committed):

```
GOOGLE_CLOUD_PROJECT=gen-lang-client-0987507894
GOOGLE_CLOUD_LOCATION=europe-west1
```

`src/config.py` already reads `.env`, so `optional("GOOGLE_CLOUD_LOCATION",
"europe-west1")` works with the existing helper.

## Step 4 — VERIFY THE SDK BEFORE WRITING AGAINST IT

This is the rule `notes/day2.md` earned on Day 2: **read the installed library,
not only the documentation.** The Google SDK's surface has moved (client
construction and the structured-output config have both changed shape across
versions), so confirm against what is actually in your `.venv`:

```bash
python -c "import google.genai as g; print(g.__version__)"
python -c "import google.genai as g; help(g.Client.__init__)"
python -c "import google.genai as g, inspect; print([m for m in dir(g.Client(vertexai=True, project='x', location='europe-west1')) if not m.startswith('_')])"
```

What you are checking:

1. how the client is told to use Vertex rather than the developer API;
2. which call produces content, and what the structured-output argument is
   called on your version;
3. how the parsed object comes back.

Write the script against what you find, not against this runbook.

## Step 5 — Get the primary source locally

The consolidated AI Act as at 27 July 2026 (post Digital Omnibus):

`https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:02024R1689-20260727`

Save the page text to a scratch file (~395k characters, roughly 100k tokens).
Keep it **out of the repo** — it is a large third-party document and the repo
hygiene rule in START-HERE §2 says only commit what the project needs. A path
under your practice/scratch folder is right.

## Step 6 — What to send

Four things, in this order:

1. the consolidated Act text;
2. `src/aiact/obligations.py` and `src/aiact/schema.py`;
3. the tier ladder from `notes/project1-spec.md` §3;
4. `notes/day2-act-review.md` — the Claude review, presented as *a claim to be
   attacked*, not as background.

## Step 7 — The instruction

Adversarial, and evidence-bound:

> You are reviewing a compliance classifier against the primary text of
> Regulation (EU) 2024/1689 as consolidated on 27 July 2026, which is supplied
> in full. A previous review by a different AI model is also supplied. Your job
> is to find where the code, the tier ladder, or that previous review is wrong.
>
> Rules:
> - Every finding must quote the specific article or annex point it relies on.
>   A finding you cannot ground in a quotation is not a finding — drop it.
> - Do not repeat findings the previous review already made correctly. Say
>   explicitly which of its findings you believe are **wrong or overstated**.
> - Where the code is right, say so and stop. Do not manufacture issues.
> - Rank by consequence: a wrong obligation list for a real ManCo scenario
>   outranks a citation formatting nit.

Ask for structured output so the findings are countable rather than prose. The
same Pydantic-class-as-schema pattern works — note the supported-keyword set
differs from Anthropic's (see Step 9).

## Step 8 — Triage the output

Three buckets, and be strict:

- **Grounded and new** → fix, and record it in `notes/day2-act-review.md`.
- **Grounded and contradicts the Claude review** → the interesting bucket. Go
  back to the Act yourself and decide. Do not take either model's word.
- **Ungrounded** → discard without argument. No quote, no finding.

Then write one line per accepted finding into the review note, and say which
model found it. That provenance is the artefact — "two providers, one primary
source, here is where they disagreed and how I resolved it" is a stronger
interview story than either review on its own.

## Step 9 — The portability finding to watch for

Anthropic's SDK **strips** `minimum`, `maximum`, `minLength`, `maxLength` and
`pattern` from the schema and appends them to the field description as text
(verified in `anthropic/lib/_parse/_transform.py`, 2026-08-31). Google's
documented schema subset **does** support `minimum`/`maximum` on numbers, and
`enum` on strings, but rejects very large or deeply nested schemas.

So the two providers enforce **different subsets of JSON Schema**. That is the
concrete, demonstrated justification for `toolkit/structured.py` existing at all
rather than calling each provider's native parse inline: the wrapper's job is to
validate what actually came back, because what the schema *promises* differs per
provider. Record whatever you observe — it is a genuine engineering finding and
most candidates cannot produce one.

## Step 10 — Cost

Roughly 100k input tokens per pass plus a few thousand out. On the GCP credit,
not the Anthropic key. Run it once; if a second pass is needed, cache or trim
the Act to the articles in scope (5, 6, 16, 23–27, 49–51, 55, 113 and Annex III)
rather than resending the whole text.

## Step 11 — Keep the script out of the repo unless it earns its place

START-HERE §2: one-off checks are commands, not committed files. If you run this
a second time, promote it to `toolkit/` with the standard docstring. Not before.
