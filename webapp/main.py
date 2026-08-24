"""Minimal web service for the Day-0 Cloud Run deploy.

Run locally:   uvicorn webapp.main:app --reload
Deploy:        gcloud run deploy hello-ai --source . --region europe-west1 --allow-unauthenticated

Kept keyless on purpose: the hello-world proves your deploy pipe works without
needing any secret in the container. Adding a Claude-powered route later is a
one-liner (see README → "Add the API key to Cloud Run").
"""
from fastapi import FastAPI

app = FastAPI(title="AI Eng Starter")


@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "Hello from Cloud Run — your deploy pipe works.",
    }


# Named /health, not /healthz: bare /healthz never reaches the container on a
# *.run.app hostname — it 404s upstream while every other path gets through.
@app.get("/health")
def health():
    return {"ok": True}
