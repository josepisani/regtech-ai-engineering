"""ui.py — the Streamlit face of Project 1.

WHAT IT DOES
    A paste box for a vendor or system description, and the validated
    inventory row that comes back: tier, role, obligations, gaps, legal basis,
    rationale. Rows accumulate for the session so a reviewer can see the actual
    point of the tool — forty descriptions become forty rows — and download
    them as CSV or JSON.

WHY IT EXISTS
    The reference checkers (Future of Life Institute; the Commission's AI Act
    Service Desk) are decision trees for someone who already knows the answers.
    This reads the answers out of unstructured text. That difference is only
    visible if you can paste a real vendor blurb and get a row, so the paste
    box IS the demo.

    Run locally:  streamlit run webapp/ui.py

HOW IT TALKS TO THE CORE
    Two modes, one code path decided by one environment variable:

      CLASSIFY_API_URL unset  -> import src.aiact.classify and call it here.
                                 One process, no network hop. This is the
                                 default and what you run locally.
      CLASSIFY_API_URL set    -> POST to that /classify endpoint instead.
                                 Same core, reached over HTTP.

    Both are thin adapters over the same function, so they cannot disagree
    about a classification. The switch exists because the interview question
    "how would this run inside a bank?" has a concrete answer: point the UI at
    an endpoint inside the perimeter and nothing else changes.

WHAT IT DELIBERATELY DOES NOT DO
    It does not write anything you paste to disk. Rows live in Streamlit's
    per-session memory and are gone when the tab closes. Nothing is persisted
    server-side, and the cost log records a character count, never characters.
"""
from __future__ import annotations

import json
import os
import time

import streamlit as st

from webapp.examples import EXAMPLES

st.set_page_config(
    page_title="EU AI Act System Inventory Classifier",
    page_icon="§",
    layout="wide",
)

API_URL = os.getenv("CLASSIFY_API_URL", "").strip()

TIER_STYLE = {
    "prohibited": ("Prohibited", "#7f1d1d"),
    "high_risk": ("High risk", "#b45309"),
    "limited_risk": ("Limited risk", "#0369a1"),
    "minimal_risk": ("Minimal risk", "#15803d"),
    "insufficient_information": ("Insufficient information", "#4b5563"),
}

DISCLAIMER = (
    "**Informational only.** These results are not legal advice — consult a "
    "qualified professional. This is not an official or authoritative "
    "assessment of your situation, and it does not create or discharge any "
    "obligation under Regulation (EU) 2024/1689."
)


# --- talking to the core ----------------------------------------------------


def _classify_in_process(description: str) -> tuple[dict, dict]:
    """Call the core directly. Imported lazily so the page renders before the
    Anthropic client is constructed — a missing API key should show as a clear
    message under the button, not as a stack trace instead of the whole page."""
    from src.aiact.classify import classify_with_meta
    from toolkit.costlog import check_spend_cap, log_call, price, record_spend

    # Before the call. In API mode the endpoint does the same check, so the cap
    # holds whichever way the UI is wired.
    check_spend_cap()

    started = time.perf_counter()
    record, result = classify_with_meta(description)
    elapsed = time.perf_counter() - started

    cost = price(result.usage, result.model)
    record_spend(cost)
    log_call(result, latency_s=elapsed, char_count=len(description), label="ui")

    return json.loads(record.model_dump_json()), {
        "model": result.model,
        "attempts": result.attempts,
        "latency_s": round(elapsed, 3),
        "input_tokens": cost.input_tokens,
        "output_tokens": cost.output_tokens,
        "cache_read_tokens": cost.cache_read_tokens,
        "cache_write_tokens": cost.cache_write_tokens,
        "total_usd": cost.total_usd,
        "cache_saved_usd": cost.cache_saved_usd,
    }


def _classify_over_http(description: str) -> tuple[dict, dict]:
    """Call the FastAPI endpoint. Same contract, different transport."""
    import httpx

    response = httpx.post(
        f"{API_URL.rstrip('/')}/classify",
        json={"description": description},
        timeout=120.0,
    )
    if response.status_code >= 400:
        # The API's own message is written to be safe to show: it describes the
        # failure without quoting what was sent.
        detail = response.json().get("detail", response.text)
        raise RuntimeError(detail)
    payload = response.json()
    return payload["classification"], payload["cost"]


def run_classification(description: str) -> tuple[dict, dict]:
    return _classify_over_http(description) if API_URL else _classify_in_process(description)


# --- rendering --------------------------------------------------------------


def render_row(record: dict, cost: dict) -> None:
    label, colour = TIER_STYLE.get(record["risk_tier"], (record["risk_tier"], "#4b5563"))

    st.markdown(
        f"<div style='display:inline-block;padding:.35rem .8rem;border-radius:.4rem;"
        f"background:{colour};color:#fff;font-weight:600;font-size:1.05rem'>{label}</div>",
        unsafe_allow_html=True,
    )

    top = st.columns(4)
    top[0].metric("System", record["system_name"] or "—")
    top[1].metric("Our role", record["effective_role"])
    top[2].metric("Confidence", record["confidence"])
    top[3].metric("Act applies", record["act_applies"])

    # The stated/effective split is the Article 25 escalation. Showing it only
    # when the two differ keeps the normal case quiet and makes the abnormal
    # one impossible to miss — which is the whole reason the record keeps both.
    if record["our_role"] != record["effective_role"]:
        st.warning(
            f"Article 25 escalation: the description states **{record['our_role']}**, "
            f"but on these facts we are the **{record['effective_role']}** and carry "
            f"provider obligations."
        )

    st.markdown(f"**Purpose.** {record['system_purpose']}")

    left, right = st.columns(2)

    with left:
        st.markdown("#### Obligations")
        if record["obligations"]:
            for item in record["obligations"]:
                st.markdown(f"- {item}")
        else:
            st.caption("None derived. Obligations are looked up in Python, never generated.")

        st.markdown("#### Legal basis")
        if record["legal_basis"]:
            st.markdown(" · ".join(f"`{b}`" for b in record["legal_basis"]))
        else:
            st.caption("No provision cited. An empty list beats a plausible citation.")

    with right:
        st.markdown("#### Gaps to put to the vendor")
        if record["gaps"]:
            for gap in record["gaps"]:
                st.markdown(f"- {gap}")
        else:
            st.caption("No open questions on the facts given.")

        if record["is_gpai"]:
            st.info(f"General-purpose AI model involved. {record.get('gpai_note') or ''}")
        if record["annex_iii_derogation"] != "none":
            st.info(
                f"Article 6(3) derogation claimed on limb "
                f"`{record['annex_iii_derogation']}` — this creates its own "
                f"documentation duty under Article 6(4)."
            )
        if record["performs_profiling"]:
            st.caption("Performs profiling of natural persons.")

    with st.expander("Rationale"):
        st.write(record["rationale"])

    with st.expander("Full record (JSON)"):
        st.json(record)

    cached = cost.get("cache_read_tokens", 0)
    cache_note = (
        f" · {cached:,} input tokens from cache, saving ${cost.get('cache_saved_usd', 0):.4f}"
        if cached
        else " · cache written (first call of the session)"
    )
    st.caption(
        f"{cost['model']} · {cost['latency_s']}s · attempts {cost['attempts']} · "
        f"${cost['total_usd']:.4f}{cache_note}"
    )


# --- page -------------------------------------------------------------------

if "rows" not in st.session_state:
    st.session_state.rows = []
if "spend" not in st.session_state:
    st.session_state.spend = 0.0

st.title("EU AI Act System Inventory Classifier")
st.caption(
    "Paste a vendor or system description. Get a validated inventory row: "
    "scope, role, tier, obligations and the questions still to ask."
)

with st.sidebar:
    st.markdown("### About")
    st.markdown(
        "Built for a Luxembourg management company building its AI system "
        "inventory under Regulation (EU) 2024/1689, as consolidated on "
        "27 July 2026."
    )
    st.markdown("### How it differs")
    st.markdown(
        "The Future of Life Institute's checker and the European Commission's "
        "AI Act Service Desk tool are decision trees: you answer the questions, "
        "they apply the logic. This reads the answers out of unstructured text, "
        "so forty vendor descriptions become forty rows — and says "
        "*insufficient information* with the questions to ask when the text "
        "does not settle it, which a form cannot do."
    )
    st.markdown("### Data handling")
    st.markdown(
        "**Controller:** the operator of this demo. **Processor:** Anthropic "
        "PBC (United States), which runs the language model that reads the "
        "description, under its own commercial terms.\n\n"
        "What you enter is sent to that API to be classified and is then "
        "discarded. It is **not stored** by this application and cannot be "
        "retrieved by its operator: rows exist only in this browser session's "
        "memory and go when you close the tab, and the cost log records how "
        "long a description was, never what it said.\n\n"
        "Server access logs hold the usual request metadata, including your IP "
        "address, for a short retention period.\n\n"
        "Please do not enter personal data or client information. Examples are "
        "provided so you do not need to."
    )
    st.markdown("### AI literacy")
    st.markdown(
        "This tool uses a large language model to read the description. It can "
        "be wrong, and it is wrong in patterns worth knowing: it under-uses "
        "*insufficient information*, and it drifts toward *high risk* around "
        "financial-services language. Treat every row as a first draft for a "
        "human reviewer, and read the rationale before accepting the tier."
    )
    if API_URL:
        st.caption(f"Calling the API at `{API_URL}`.")
    else:
        st.caption("Calling the classifier in-process.")

# Article 50(1): tell the person they are interacting with an AI system, at the
# point of interaction rather than buried in a footer.
st.info(
    "You are interacting with an AI system. Its output is generated by a "
    "language model and is marked as machine-generated in every record."
)

# --- Input: examples first, free text by deliberate choice -------------------
# The ordering is the privacy control. A free text box as the default path on a
# public page invites a pasted CV or client name, and receiving one makes the
# operator a controller of it. Most visitors want to see what the tool does,
# which an example answers; the ones who type are then a much smaller group who
# have read a warning first. Capability is unchanged — only the default is.
source = st.radio(
    "What would you like to classify?",
    ["An example", "My own description"],
    horizontal=True,
    label_visibility="collapsed",
)

if source == "An example":
    choice = st.selectbox("Pick an example", list(EXAMPLES))
    description = EXAMPLES[choice]
    st.text_area("Description", value=description, height=170, disabled=True)
else:
    # Article 13 in the place it is actually read: beside the box, before the
    # paste, not in a policy page nobody opens.
    st.warning(
        "**Please do not paste personal data or client information.** "
        "What you enter is sent to Anthropic's API to be classified and is then "
        "discarded — it is not stored by this application and cannot be retrieved "
        "by its operator. Anthropic processes it in the United States under its "
        "own commercial terms. Use invented or public descriptions."
    )
    description = st.text_area(
        "Vendor or system description",
        height=200,
        max_chars=8_000,
        placeholder=(
            "e.g. NavGuard. Runs overnight on our fund accounting extracts and "
            "flags NAV movements that look anomalous versus the prior 60 days, so "
            "the valuation team can investigate before sign-off."
        ),
    )

go = st.button("Classify", type="primary", disabled=not (description or "").strip())

if go:
    from src.aiact.classify import DescriptionTooLongError, validate_description

    try:
        cleaned = validate_description(description)
    except DescriptionTooLongError as exc:
        st.error(str(exc))
    except ValueError as exc:
        st.error(str(exc))
    else:
        with st.spinner("Reading the description against the Act…"):
            try:
                record, cost = run_classification(cleaned)
            except Exception as exc:  # noqa: BLE001 — the page must not crash
                # The message is shown; the description is not repeated back,
                # here or anywhere else.
                st.error(f"Classification failed: {exc}")
                st.caption(
                    "If this says the API key is missing, set ANTHROPIC_API_KEY "
                    "in your .env and restart. Nothing you pasted was sent anywhere "
                    "if the call never opened."
                )
            else:
                st.session_state.rows.append(record)
                st.session_state.spend += float(cost.get("total_usd", 0.0))
                render_row(record, cost)

if st.session_state.rows:
    st.divider()
    st.subheader(f"This session — {len(st.session_state.rows)} row(s)")
    st.caption(f"Total spend this session: ${st.session_state.spend:.4f}")

    columns = [
        "system_name",
        "provider_name",
        "act_applies",
        "our_role",
        "effective_role",
        "risk_tier",
        "annex_iii_derogation",
        "performs_profiling",
        "is_gpai",
        "confidence",
        "classified_at",
        "ruleset_version",
    ]
    table = [{c: row.get(c) for c in columns} for row in st.session_state.rows]
    st.dataframe(table, width="stretch", hide_index=True)

    import csv
    import io

    buffer = io.StringIO()
    # The export carries ai_generated so an Article 50(2) marking survives the
    # trip into whatever register the row ends up in.
    fieldnames = columns + ["legal_basis", "obligations", "gaps", "rationale", "ai_generated"]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in st.session_state.rows:
        flat = {c: row.get(c) for c in columns}
        flat["legal_basis"] = "; ".join(row.get("legal_basis") or [])
        flat["obligations"] = "; ".join(row.get("obligations") or [])
        flat["gaps"] = "; ".join(row.get("gaps") or [])
        flat["rationale"] = row.get("rationale")
        flat["ai_generated"] = True
        writer.writerow(flat)

    downloads = st.columns(3)
    downloads[0].download_button(
        "Download CSV",
        buffer.getvalue(),
        file_name="ai_act_inventory.csv",
        mime="text/csv",
    )
    downloads[1].download_button(
        "Download JSON",
        json.dumps(
            [{**row, "ai_generated": True} for row in st.session_state.rows], indent=2
        ),
        file_name="ai_act_inventory.json",
        mime="application/json",
    )
    if downloads[2].button("Clear session"):
        st.session_state.rows = []
        st.session_state.spend = 0.0
        st.rerun()

st.divider()
st.caption(DISCLAIMER)
