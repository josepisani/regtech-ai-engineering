# AGENTS.md — standing context for the ai-eng-starter repo

## What this repo is
A 20-day AI-engineer portfolio sprint. The **full plan lives in the Codex.ai
project doc `Codex/START-HERE.md`** — not in this repo. This file is standing
context only. **Never propose a new plan, roadmap, or reordering of days.**
If asked "what should I do next," the answer is: check START-HERE in the
Codex.ai project.

## The three projects (decided 2026-08-26 — do not substitute)
1. **EU AI Act Vendor Classifier** (`src/`, Days 2–4): vendor/system description
   → validated JSON — risk tier (prohibited/high-risk/limited/minimal + GPAI),
   obligations, missing-info gaps, rationale. Tool calling + Pydantic +
   retry-on-invalid. Streamlit or FastAPI → Cloud Run.
2. **Regulatory Q&A RAG** (Days 6–9): public texts only (EU AI Act, DORA,
   AIFMD II, CSSF 18/698, ESMA CSA, SFDR) → citations at article level,
   clean refusal when the corpus lacks the answer.
3. **Delegation Oversight Agent** (Days 11–15): synthetic delegate pack →
   LangGraph agent → committee-ready review memo with cited exceptions table.
   Missing data becomes a finding, never an invention.

## Working discipline
- **Direct → review → understand → debug.** Build in pieces; the user reads and
  can explain every piece before accepting. When asked, explain code line by
  line rather than regenerating it.
- The user does 1h/day with autocomplete off; don't undermine that by dumping
  large unrequested code blocks during learning blocks.
- Work on a `dayN` branch, never directly on `main`.

## Hard rules (never violate)
- **Secrets:** only in `.env`, which is git-ignored. Never print, commit, or
  echo the API key. If `.env` shows up in `git status`, stop and fix
  `.gitignore` first.
- **No confidential or employer data — ever.** Public or synthetic data only.
  Nothing resembling a JSSFML document, template, contract, or delegate list.
- **No scratch files in commits.** `scratch_*.py` is deleted before commit.
  Only commit files the project needs.
- **Scope guard:** each project ships at its "Done when" bar (see START-HERE).
  No accounts, scrapers, n8n, or extra features — this sprint is not the SaaS.

## Environment
- Python 3.11 via `uv`; venv in `.venv` (git-ignored). After any pull:
  `uv venv --python 3.11` → activate → `uv pip install -r requirements.txt`.
- **Two machines.** Windows (day): `.venv\Scripts\activate`, `py` launcher.
  Mac (night): `source .venv/bin/activate`, `python`. GitHub is the only sync
  bridge — pull on sit-down, push before stopping. `.env` is recreated by hand
  on each machine.
- Models: experiments on `Codex-haiku-4-5-20251001`; output tokens cost 5×
  input across the lineup. GCP project `gen-lang-client-0987507894`,
  region `europe-west1`, deploys to Cloud Run.

## Repo layout
- `src/` — real, committed code (e.g. `llm_probe.py`)
- `toolkit/` — reusable utilities promoted from daily work (each file needs a
  docstring: what/why/how, and must be imported by a project to stay)
- `notes/dayN.md` — daily notes, definitions, cost tables, running log

## Editing files in this repo — read before any automated edit

Added 2026-09-02 after an automated edit to `.gitignore` mangled the whole
file and briefly un-ignored `.env`. The rules that would have prevented it:

- **Check the file's line endings before writing it back.** This repo is
  mixed: `AGENTS.md` is CRLF, `.gitignore` is LF. Never assume; read the
  bytes, or use an operation that cannot care.
- **Use the most boring operation that does the job.** Append to append; one
  exact, unique replace to change one thing. No chained transformations over
  whole-file contents — every extra step is a way to destroy the parts you
  were not editing.
- **`git status` showing many files modified with equal insertions and
  deletions is not a real change.** It is an artifact of reading these
  Windows working files through a Linux shell. Confirm with
  `git diff --ignore-all-space --stat` (empty output = whitespace only) and
  do NOT rewrite file contents to work around it.
- **Verify the diff after writing, not just that the write succeeded.** Use
  `git diff --ignore-all-space --stat <file>`, not plain `--stat`: because of
  the artifact above, plain `--stat` reports the whole file as rewritten and
  you cannot tell a real deletion from noise. Ignoring whitespace, an append
  must show insertions only. If it shows deletions you destroyed something —
  restore with `git checkout -- <file>` and start again.
- **Extra care near anything holding secrets** — `.gitignore`, `.env.example`,
  deploy config. After touching them, re-check the protection still works:
  `git check-ignore -v .env` must print a matching rule.
