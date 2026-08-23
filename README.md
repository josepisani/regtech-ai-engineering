# <Project name>

> One line: what problem this solves and for whom.

**Live demo:** <your Cloud Run URL>
**Stack:** Python · Anthropic Claude API · <Gemini embeddings / pgvector / LangGraph as relevant> · Google Cloud Run

## What it does
2–3 sentences. Lead with the user-facing outcome, not the implementation.

## Architecture
A short description or a simple diagram. For an AI app, name: the model(s), how
context is assembled, where state lives, and how it's deployed.

```
user → app (FastAPI/Streamlit) → Claude API
                               ↘ (RAG) Gemini embeddings → pgvector
```

## Evaluation
The part most portfolios skip — so it's the part that stands out. Summarize:
- the test set (how many examples, how labeled)
- the metrics (e.g. retrieval hit-rate, answer correctness)
- before/after any improvement you made

## Run it locally
```bash
# 1. Clone and enter
git clone <repo-url> && cd <repo>

# 2. Create a virtual env and install deps (uv)
uv venv --python 3.11        # creates .venv (uv fetches Python 3.11 if missing)
source .venv/bin/activate
uv pip install -r requirements.txt

# 3. Configure secrets (never commit .env)
cp .env.example .env      # then fill in your keys

# 4. Prove the Claude pipe
python -m src.hello_claude       # calls the Claude API, prints token cost
```

## Deploy the hello-world to Cloud Run
```bash
# one-time: point gcloud at your project
gcloud config set project $GOOGLE_CLOUD_PROJECT
gcloud services enable run.googleapis.com cloudbuild.googleapis.com

# deploy straight from source (builds the Dockerfile for you)
gcloud run deploy hello-ai \
  --source . \
  --region europe-west1 \
  --allow-unauthenticated
```
When it finishes it prints a public URL. Open it — you should see the "your
deploy pipe works" JSON. That's the Day-0 deploy task done.

### Add the API key to Cloud Run (later, when a route calls Claude)
```bash
echo -n "$ANTHROPIC_API_KEY" | gcloud secrets create anthropic-api-key --data-file=-
gcloud run deploy hello-ai --source . --region europe-west1 \
  --set-secrets ANTHROPIC_API_KEY=anthropic-api-key:latest
```

## Configuration
All config is read from environment variables (see `.env.example`). Nothing
secret is hard-coded or committed.

## Notes
- Claude runtime calls are billed to your Anthropic API key (separate from a Max plan).
- BigQuery / Cloud Run usage is billed to your Google Cloud project (free-trial credit).
