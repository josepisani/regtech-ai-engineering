# Code review brief — EU AI Act Vendor Classifier (Project 1)

*Prepared 2026-09-15 for an external reviewer with read access to the repo.
Review target: branch `main` at commit `b5a6e47`. Everything on `day4` is
work in progress and out of scope.*

---

## 1. What you are reviewing, and for whom

A Python 3.11 tool that turns an unstructured vendor/system description into a
validated EU AI Act inventory record: does the Act apply, whose obligations are
they (provider/deployer, with Art. 25 escalation), which risk tier, on what
legal basis, which obligations, and which questions the text left unanswered.
One core (`src/aiact/`) behind two thin adapters (Streamlit UI, FastAPI
endpoint), built on a small reusable toolkit (`toolkit/`).

**Who will read this code after you:** hiring managers for AI-engineering
roles, and Conducting Officers / Heads of Risk at Luxembourg management
companies deciding whether to trust the author with their compliance tooling.
The author is a CFA charterholder and Deputy Head of Risk at a CSSF-regulated
ManCo, learning to build; the code was written with an AI pair over ~1 h/day.

**So the review has two questions, in this order:**

1. **Is it correct and safe?** Does it do what the README claims, and can it
   leak a secret or a user's input?
2. **Does it read as professional engineering?** What would make a senior
   engineer skimming this for ten minutes lower their opinion — and what is the
   cheapest fix?

The domain logic (which article applies when) has been reviewed by the author
against the Act and is **not** what I need from you. If you spot a legal error,
note it, but do not spend your time there.

## 2. Setup (10 minutes)

```bash
git clone <repo> && cd ai-eng-starter && git checkout b5a6e47
uv venv --python 3.11 && source .venv/bin/activate   # Windows: .venv\Scripts\activate
uv pip install -r requirements.txt
python -m pytest -q          # expect: 33 passed, 4 skipped (the 4 need an API key)
```

You do **not** need an API key. Everything except four live tests runs
offline; `tests/conftest.py` contains a fake Anthropic client that drives the
truncation, refusal and retry paths deterministically. If you want to run the
four live tests or the UI, create `.env` from `.env.example` with your own key
— each classification costs about $0.003.

To see the UI: `streamlit run webapp/ui.py`. To see the API:
`uvicorn webapp.main:app` then open `/docs`.

## 3. Map of the code (3,770 lines total, ~2,000 that matter)

| Path | Lines | What it is | Review priority |
|---|---|---|---|
| `toolkit/structured.py` | 293 | `call_schema`: Pydantic schema → validated object, retry on invalid output feeding the exact error back, refusal/truncation handling, prompt-cache helper | **High** — the load-bearing abstraction |
| `src/aiact/classify.py` | 401 | System prompt (rules + 5 few-shot examples), input validation, the one call into `call_schema`, CLI | **High** |
| `src/aiact/schema.py` | 385 | The output contract: enums for each gate, `ModelVerdict` (what the model returns) → `Classification` (what the tool returns, with obligations attached) | **High** — every consumer depends on it |
| `toolkit/costlog.py` | 335 | Pricing table keyed by model id, per-call cost, in-process spend cap, `log_call` designed so it *cannot* receive the input text | **High** for the privacy claim |
| `webapp/main.py` | 231 | FastAPI adapter: request validation, error responses that never echo the input, spend-cap → 429 | **High** for the privacy claim |
| `webapp/ui.py` | 426 | Streamlit adapter: examples-first UI, session-only rows, CSV/JSON export, disclaimer, `sys.path` fix at top | Medium |
| `src/aiact/obligations.py` | 403 | Rule tables: tier × role → obligation text with article references | Low (content, not logic) |
| `src/aiact/compare.py` | 114 | Eval harness: runs 20 labelled rows, diffs predictions vs labels | Medium |
| `tests/test_edge_cases.py` | 509 | 31 tests — input limits, truncation/refusal/retry, caching invariants, cost arithmetic, privacy invariants, Art. 6/25 logic, four live edge cases | **High** — tell me what they *don't* cover |
| `tests/conftest.py` | 140 | Fake Anthropic client | Medium |
| `Dockerfile`, `.dockerignore` | 75 | One image, `APP_MODE=ui\|api` switch, `PYTHONUNBUFFERED` | Medium |
| `src/llm_probe.py`, `src/hello_claude.py`, `src/config.py` | 291 | Day-1/2 learning scripts, kept as history | Skip unless something is embarrassing |
| `webapp/examples.py` | 70 | Four synthetic demo inputs | Skip |
| `data/*.jsonl` | — | 20 synthetic vendor descriptions, hand labels, one prediction snapshot | Skip |
| `notes/*.md` | — | Daily engineering notes; `notes/day3.md` has the error analysis | Read `day3.md` §"six patterns" for context only |

The daily notes are honest and long. They will tell you *why* most decisions
were made; if a decision looks wrong, check whether the note already
considered it before writing it up.

## 4. What I specifically want checked

### 4.1 Secrets and input privacy — the claims that must be true
The README says: nothing a user pastes is stored, logged, or echoed back; the
API key is only ever in `.env`. Please try to break both:
- Any path where the description reaches a log line, an exception message, a
  traceback, a 422/500 body, Streamlit's own logging, or uvicorn's access log.
  `webapp/main.py` deliberately avoids Pydantic's `max_length=` because its
  error carries the value — check nothing else does the same thing.
- `toolkit/costlog.log_call` has no parameter that could take the text, and a
  test asserts the signature. Is that test actually strong, or does it pass by
  accident?
- `.gitignore`, `.dockerignore`, `.env.example`: anything that could let `.env`
  into a commit or an image. Note: there is no `.gcloudignore` (gcloud derives
  one from `.gitignore` — is that reliance acceptable?).
- `git log -p` for anything that ever should not have been committed.

### 4.2 `toolkit/structured.py` — the retry loop
- The `max_tokens` doubling on truncation resets `messages` to the original
  prompt; the validation-error retry appends assistant + user turns. Is the
  interaction between the two branches correct across three attempts?
- `parsed_output` is used when present, else raw text is re-parsed. Is there a
  case where a *wrong* parsed object is accepted without validation?
- Exception hierarchy (`StructuredError` → `RefusalError`,
  `SchemaRetryError`): does every failure path raise one of them, or can a raw
  `anthropic.*` exception escape to the adapters?

### 4.3 The output contract
- `ModelVerdict` vs `Classification`: `Classification.from_verdict` attaches
  obligations and `ruleset_version`. Is the split clean, or is there logic
  that belongs on one side and sits on the other?
- `ai_generated: true` is added by the API response model and the UI exports,
  **not** by `Classification` itself. The author knows; opinion wanted on
  whether it belongs in the core record.
- Enums are `str, Enum`. Anything about them that will bite when the schema
  is sent as JSON Schema to the model?

### 4.4 Spend cap and concurrency
`costlog._spent_usd` is a module-level float: per process, unguarded. Under
uvicorn with one worker it is fine; under Streamlit's threads or multiple
Cloud Run instances it is not a cap. The author knows it is per-instance (the
comment says so). Is the *in-process* accounting thread-safe enough for
Streamlit, and is the 429 path in `main.py` correct?

### 4.5 Tests — what is missing
31 offline tests pass in 1.4 s. I want the list of behaviours that are
**claimed in the README or in comments but have no test**, ranked by how
embarrassing a regression would be. I also want to know whether any test can
pass without exercising the thing it names (see `notes/day3.md` — one such
test was found: it could not reproduce Streamlit's import-path failure).

### 4.6 Reads-as-professional
Ten-minute skim as a senior engineer. What stands out negatively? Candidates I
already suspect: comment density (very high, by design — tell me if it crosses
into noise), the Day-1 scripts still in `src/`, the length of `ui.py`,
`requirements.txt` carrying `google-cloud-bigquery` and `db-dtypes` that
nothing imports.

## 5. Known issues — do not re-discover these

| Issue | Status |
|---|---|
| Tier accuracy is 13/20 on the labelled set; six named error patterns; the largest is a missing schema field for Art. 3(1) "is this an AI system at all" | Known, documented in README and `notes/day3.md`; fix scheduled |
| Model invents a "materially affects" qualifier when ruling out Art. 50(1) (still reaches the right tier via 50(2)) | Found 2026-09-15; likely leakage from the InterviewScribe few-shot; not yet fixed |
| Latency 6–10 s per call at ~7.2k input tokens | Measured, not yet investigated |
| Spend cap is per process/instance | Known; deploy will use `--max-instances` |
| `ai_generated` not in the core `Classification` record | Known; see 4.3 |
| Unused `google-cloud-bigquery`, `db-dtypes` in requirements | Known |
| No `.gcloudignore` | Known |
| `confidence` calibration 8/20 | Known; low priority |

## 6. Ground rules

- **No confidential or employer data exists in this repo, and none may be
  added.** Every description is synthetic. If anything looks like a real
  vendor, a real fund, or a real person, flag it as a finding — it should not
  be there.
- **Do not commit.** Findings come back as a document (format below), or as a
  branch `review/<your-name>` with commits I can read. Nothing to `main`.
- Do not add or run anything that needs an API key unless you use your own.
- The author is learning: for every finding, the *why* matters more than the
  patch. A fix without an explanation will be reverted until it is understood.

## 7. What to hand back

One Markdown document, findings ordered by severity, each with:

```
### <short title>
Severity: blocker | should-fix | nice-to-have | style
Where: path:line
What: one or two sentences — what is wrong or weak
Why it matters: who is affected, what breaks, or what a reader concludes
Fix: the smallest change that resolves it (a diff is welcome, not required)
Confidence: high | medium — say when you are not sure
```

Plus, at the end, three lists:
1. Behaviours with no test (from 4.5), ranked.
2. Things you checked and found sound — so I know what was covered, not only
   what was wrong.
3. Anything you would want to see before recommending this author for a
   mid-level AI-engineering role.

Time budget I am paying for: state it back to me before you start, and stop
at it. A partial review with a clear "not reached" list beats a rushed
complete one.
