"""main.py — the HTTP face of Project 1.

WHAT IT DOES
    GET  /            service banner
    GET  /health      liveness probe
    POST /classify    one description in, one validated inventory row out

WHY IT EXISTS
    The classification logic lives in src/aiact/classify.py and knows nothing
    about HTTP. This file is a thin adapter over it: it validates input, maps
    the core's exceptions onto status codes, and prices the call. The Streamlit
    UI is a second adapter over the same core. Neither can change the answer,
    which is what makes it defensible to say the API and the UI agree.

    Run locally:  uvicorn webapp.main:app --reload
    Then:         curl -s localhost:8000/classify -H 'content-type: application/json' \
                       -d '{"description":"..."}' | python -m json.tool

WHAT IT DELIBERATELY DOES NOT DO
    It does not log the description, echo it in an error, or keep it after the
    response is written. See the DATA HANDLING block below — that is a promise
    made on the page and in the README, and it is only true if it is true here.
"""
from __future__ import annotations

import logging
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.aiact.classify import (
    MAX_DESCRIPTION_CHARS,
    MODEL,
    DescriptionTooLongError,
    classify_with_meta,
    validate_description,
)
from src.aiact.schema import Classification
from toolkit.costlog import SpendCapExceeded, check_spend_cap, log_call, price, record_spend
from toolkit.structured import RefusalError, SchemaRetryError, StructuredError

# --- DATA HANDLING ----------------------------------------------------------
# Nothing a caller sends is written anywhere. Concretely:
#   * no handler logs `body.description`, and none of them may start to;
#   * uvicorn's access log records method, path and status — never the body;
#   * toolkit.costlog.log_call has no parameter for the text (by design) and
#     is given only a character count;
#   * error responses describe the failure without quoting the input, so a
#     description cannot arrive in an error-tracking tool by the back door.
# The one place this is easy to break is a debug `logger.info(f"...{body}")`
# added while chasing a bug and never removed. Don't.
logger = logging.getLogger("aiact")

app = FastAPI(
    title="EU AI Act System Inventory Classifier",
    description=(
        "Turns an unstructured vendor or system description into a validated "
        "AI Act inventory row. Informational only; not legal advice."
    ),
    version="1.0.0",
)


class ClassifyRequest(BaseModel):
    description: str = Field(
        ...,
        description=(
            f"The vendor or system description to classify. "
            f"Maximum {MAX_DESCRIPTION_CHARS:,} characters."
        ),
        # NOT max_length=. That looks like the obvious way to write this and it
        # leaks: Pydantic's string_too_long error carries the offending value in
        # its `input` field, and FastAPI's default handler serialises the whole
        # error list into the 422 body — so an over-long paste comes straight
        # back to the caller, and into any error tracker watching 4xx bodies.
        # Found by a test on 2026-09-10, not by reading the code.
        #
        # The length check therefore happens in validate_description, in the
        # core, where the UI hits the same rule. json_schema_extra still puts
        # the ceiling in the OpenAPI document for anyone generating a client.
        json_schema_extra={"maxLength": MAX_DESCRIPTION_CHARS},
    )


class CallCost(BaseModel):
    """What the call cost. Returned so the UI never re-derives pricing."""

    model: str
    attempts: int
    latency_s: float
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    total_usd: float
    cache_saved_usd: float


class ClassifyResponse(BaseModel):
    # Article 50(2): the record must say it was machine-generated. It is a
    # field rather than a note in the docs so that it survives being exported
    # to CSV, pasted into a register, or read six months later by someone who
    # never saw this page.
    ai_generated: bool = True
    classification: Classification
    cost: CallCost


@app.exception_handler(RequestValidationError)
async def scrub_validation_errors(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Return validation errors without the value that caused them.

    Belt to the braces on the field above. FastAPI's default handler includes
    each error's `input` — the actual value sent — and `ctx`, which can also
    carry it. On a service whose whole input is text a stranger pasted, that
    turns any malformed request into a copy of that text sitting in a response
    body and in whatever reads 4xx responses downstream.

    Dropping the two keys leaves `type`, `loc` and `msg`, which is everything a
    caller needs to fix their request and nothing that repeats what they sent.
    """
    safe = [
        {k: v for k, v in error.items() if k not in {"input", "ctx"}} for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": safe})


@app.get("/")
def root() -> dict[str, object]:
    return {
        "status": "ok",
        "service": "EU AI Act System Inventory Classifier",
        "model": MODEL,
        "endpoints": ["/health", "/classify", "/docs"],
        "disclaimer": (
            "Informational only. Not legal advice, and not an official or "
            "authoritative assessment of your situation."
        ),
    }


# Named /health, not /healthz: bare /healthz never reaches the container on a
# *.run.app hostname — it 404s upstream while every other path gets through.
@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/classify", response_model=ClassifyResponse)
def classify_endpoint(body: ClassifyRequest) -> ClassifyResponse:
    """Classify one description.

    Status codes, and why each is the one it is:
        422  the input cannot be classified (empty, too long), or the model
             refused. The caller must change what they sent; retrying will not
             help, and a 5xx would wrongly invite a retry.
        502  the model was reached but produced nothing usable after every
             attempt, or the upstream API failed. Not the caller's fault, and
             retrying may work.
    """
    try:
        description = validate_description(body.description)
    except DescriptionTooLongError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Before the call, not after: the cap is a ceiling on what has been spent
    # when a call starts, so it can be overshot by at most one call. 429 rather
    # than 402 or 503 — this is rate limiting, the limiter is spend rather than
    # requests, and a client that backs off and retries is doing the right thing.
    try:
        check_spend_cap()
    except SpendCapExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc

    started = time.perf_counter()
    try:
        record, result = classify_with_meta(description)
    except RefusalError as exc:
        raise HTTPException(
            status_code=422,
            detail="The model declined to classify this description.",
        ) from exc
    except SchemaRetryError as exc:
        # exc carries the last validation error, which is about OUR schema, not
        # about the caller's text — safe to surface and genuinely useful.
        raise HTTPException(
            status_code=502,
            detail=f"No valid classification after {exc.attempts} attempts: {exc.last_error}",
        ) from exc
    except StructuredError as exc:
        raise HTTPException(status_code=502, detail=f"Classification failed: {exc}") from exc
    except Exception as exc:  # upstream API errors, network, auth
        # logger.EXCEPTION would write the full traceback, and a traceback can
        # carry the request: an SDK error for a malformed request may quote the
        # body it sent, and that body is the description. Low probability, and
        # exactly the leak this service says does not happen — so the type name
        # is logged and nothing else.
        #
        # That is a real cost: debugging a 502 from the log alone is harder. It
        # is the right trade for a public paste box, and the fix when you need
        # more is to reproduce it locally with a description of your own, where
        # a full traceback is free.
        logger.error("classify failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=502, detail="The classification service is unavailable."
        ) from exc
    elapsed = time.perf_counter() - started

    cost = price(result.usage, result.model)
    record_spend(cost)
    log_call(result, latency_s=elapsed, char_count=len(description), label="api")

    return ClassifyResponse(
        classification=record,
        cost=CallCost(
            model=result.model,
            attempts=result.attempts,
            latency_s=round(elapsed, 3),
            input_tokens=cost.input_tokens,
            output_tokens=cost.output_tokens,
            cache_read_tokens=cost.cache_read_tokens,
            cache_write_tokens=cost.cache_write_tokens,
            total_usd=cost.total_usd,
            cache_saved_usd=cost.cache_saved_usd,
        ),
    )
