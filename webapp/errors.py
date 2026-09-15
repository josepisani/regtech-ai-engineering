"""errors.py — the one place a failure is turned into words a stranger may see.

WHY IT EXISTS
    Both adapters used to build their own error text, and both leaked. The API
    returned `SchemaRetryError.last_error` in a 502, which is Pydantic's
    validation message, which quotes the rejected value — and on this project
    the rejected value can be a field the model filled from the description.
    The Streamlit page showed `str(exc)` for every exception, including SDK
    errors that can carry the request they were sent. Found in the 2026-09-15
    review with a sentinel that came straight back in the response body.

    So: every failure maps to a FIXED sentence here, chosen by exception type,
    never by exception text. The only text passed through is our own —
    `SpendCapExceeded` and `ApiError`, both written by this codebase.

HOW TO USE IT
    from webapp.errors import ApiError, record_failed_spend, safe_error_message

    try:
        record, result = classify_with_meta(text)
    except StructuredError as exc:
        record_failed_spend(exc)              # the failed calls were billed too
        show(safe_error_message(exc))
"""
from __future__ import annotations

from toolkit.costlog import SpendCapExceeded, price, record_spend
from toolkit.structured import RefusalError, SchemaRetryError, StructuredError


class ApiError(RuntimeError):
    """The FastAPI endpoint answered 4xx/5xx. Its `detail` is our own safe text."""


def safe_error_message(exc: BaseException) -> str:
    """A sentence about the failure that repeats nothing the user entered.

    The mapping is by type. Nothing here reads `str(exc)` except for the two
    exception classes this codebase writes itself.
    """
    if isinstance(exc, (SpendCapExceeded, ApiError)):
        return str(exc)
    if isinstance(exc, RefusalError):
        return "The model declined to classify this description."
    if isinstance(exc, SchemaRetryError):
        return (
            f"The model returned an invalid classification after "
            f"{exc.attempts} attempt(s). Retrying may work."
        )
    if isinstance(exc, StructuredError):
        return "Classification failed before a record was produced."
    return f"The classification service is unavailable ({type(exc).__name__})."


def record_failed_spend(exc: StructuredError) -> None:
    """Charge the cap for a classification that produced no record.

    A refusal is one billed call; an exhausted retry is up to `max_attempts`
    of them. Before this existed, both adapters recorded spend only after a
    success, so a stream of failing requests could run against a personal API
    key for as long as it liked while the cap read zero.
    """
    if exc.usage is not None and exc.model:
        record_spend(price(exc.usage, exc.model))
