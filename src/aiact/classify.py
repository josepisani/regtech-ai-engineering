"""classify.py — one vendor description in, one validated inventory row out.

WHAT IT DOES
    classify(text) -> Classification. Builds the prompt, calls the model through
    toolkit.structured, then adds the Python-derived fields.

WHY IT EXISTS
    This is the core of Project 1. Day 3 wraps it in a UI; Day 4 deploys it.
    Nothing in this file knows about Streamlit or HTTP, so both of those can be
    added without touching the classification logic.

HOW TO USE IT
    from src.aiact.classify import classify
    record = classify("Vendor description text ...")
    print(record.risk_tier, record.obligations)

    Or from the command line:
        python -m src.aiact.classify "some vendor description"
        cat description.txt | python -m src.aiact.classify

DESIGN NOTE — one call, not three
    The spec's decomposition (extract -> classify -> derive) is deliberately NOT
    implemented yet. One call with a good schema first; split only where a
    traced failure justifies it. The 'derive' step is already split out, but
    into Python (obligations.py), which is cheaper and cannot hallucinate.
"""
from __future__ import annotations

import sys
import json

from anthropic import Anthropic
from dotenv import load_dotenv

from src.aiact.schema import Classification, ModelVerdict
from toolkit.structured import SchemaRetryError, StructuredResult, cached_system, call_schema

load_dotenv()

MODEL = "claude-haiku-4-5"

# Longest description we will pay to classify. A vendor description that says
# what the system does fits in a few hundred words; anything past this is a
# pasted contract, a whole policy, or a mistake, and all three cost real money
# at input prices before telling us anything useful. Rejecting it in Python is
# free; discovering it in the bill is not.
#
# 8,000 characters is ~2,000 tokens — roughly four times the longest of the
# twenty labelled descriptions, so it rejects accidents without clipping real
# input. Raise it if a genuine description is ever refused; do not remove it.
MAX_DESCRIPTION_CHARS = 8_000

# The few-shot examples are chosen, not collected. Five cases, each carrying one
# lesson the instructions alone do not reliably teach:
#
#   1 TalentFirst  - the textbook Annex III high-risk case, and profiling=true
#   2 NavGuard     - important, expensive, regulated AND minimal risk
#   3 Cognita      - "I cannot classify this" is a permitted answer
#   4 SentinelPay  - the Annex III 5(b) financial-fraud CARVE-OUT
#   5 InterviewScribe - the Article 6(3) DEROGATION, and why it is not the same
#                       thing as the carve-out. Reviewed 2026-09-10: the
#                       conditions for limb (d) are stated as facts in the
#                       description, Art. 50 is assessed separately before
#                       minimal_risk, and the GPAI fact is in the text rather
#                       than assumed. Example 1 is the deliberate contrast:
#                       same Annex III point, but ranking = profiling = no limb.
#
# Examples 2 and 4 do the most work. A model asked to classify anything in a
# financial firm drifts toward high_risk, because the surrounding language is
# full of risk, regulation and client money. Annex III is about a specific list
# of uses, mostly concerning decisions about people.
#
# Examples 4 and 5 must be read together, because they are two different
# mechanisms that both end in "not high-risk" and are constantly confused:
#   - a CARVE-OUT is written into the Annex III entry itself. The system never
#     enters Annex III at all, so no derogation is claimed and Art. 6(4) never
#     fires. Fraud detection under 5(b) is one.
#   - a DEROGATION under Art. 6(3) applies to a system that IS in Annex III and
#     is lifted back out. It creates its own duties under Art. 6(4).
FEW_SHOT = """
<example>
<description>
TalentFirst AI Screener. Uploads a job posting and a batch of CVs, then returns
a ranked shortlist with a fit score per candidate. Used by our HR team for the
first sift on operations roles. SaaS, hosted by the vendor in Ireland.
</description>
<answer>
{"system_name": "TalentFirst AI Screener",
 "provider_name": "TalentFirst",
 "system_purpose": "Ranks and scores job applicants' CVs to produce a shortlist for recruiters.",
 "act_applies": "applies",
 "exclusion_ground": "none",
 "our_role": "deployer",
 "art25_trigger": "none",
 "risk_tier": "high_risk",
 "annex_iii_derogation": "none",
 "performs_profiling": true,
 "is_gpai": false,
 "gpai_note": null,
 "legal_basis": ["Annex III 4(a)"],
 "rationale": "The system is used for recruitment and specifically to filter applications and evaluate candidates, which is the Annex III point 4(a) use case. We buy and use it under the vendor's name with no modification, so Article 25 does not escalate our role and we remain the deployer. It scores individual candidates, which is profiling of natural persons, so no Article 6(3) derogation could apply even if a limb otherwise fitted.",
 "gaps": ["Does the vendor supply instructions for use and a declaration of conformity?", "Are the ranking outputs logged, and for how long?"],
 "confidence": "high"}
</answer>
</example>

<example>
<description>
NavGuard. Runs overnight on our fund accounting extracts and flags NAV movements
that look anomalous versus the prior 60 days, so the valuation team can
investigate before sign-off. Trained on our own historical NAV series. Built by
our data team.
</description>
<answer>
{"system_name": "NavGuard",
 "provider_name": null,
 "system_purpose": "Flags anomalous NAV movements in fund accounting data for human investigation before sign-off.",
 "act_applies": "applies",
 "exclusion_ground": "none",
 "our_role": "provider",
 "art25_trigger": "none",
 "risk_tier": "minimal_risk",
 "annex_iii_derogation": "none",
 "performs_profiling": false,
 "is_gpai": false,
 "gpai_note": null,
 "legal_basis": [],
 "rationale": "Anomaly detection on fund valuation data is not a listed Annex III use: it makes no decision about a natural person, performs no biometric or emotion processing, and is not a safety component of a regulated product. It is operationally critical and may be significant under other regimes, but criticality is not an AI Act tiering criterion. Built in-house, so we are the provider from the outset rather than by escalation.",
 "gaps": ["Is any output ever used to assess an individual employee's performance? That would change the analysis under Annex III 4(b)."],
 "confidence": "high"}
</answer>
</example>

<example>
<description>
We are looking at Cognita for the operations team. It uses AI to make the team
more efficient and reduce manual work. Enterprise pricing, SOC 2 certified.
</description>
<answer>
{"system_name": "Cognita",
 "provider_name": "Cognita",
 "system_purpose": "Stated only as improving operational efficiency and reducing manual work; the actual function is not described.",
 "act_applies": "applies",
 "exclusion_ground": "none",
 "our_role": "deployer",
 "art25_trigger": "none",
 "risk_tier": "insufficient_information",
 "annex_iii_derogation": "none",
 "performs_profiling": false,
 "is_gpai": false,
 "gpai_note": null,
 "legal_basis": [],
 "rationale": "This is a commercial procurement by a firm established in the EU, so the Regulation applies; what is missing is the function, not the scope. The description states a benefit rather than a task. Without knowing what the system does, what data it processes, and whether its outputs affect decisions about natural persons, no tier can be assigned. SOC 2 certification concerns information security controls and says nothing about AI Act classification.",
 "gaps": ["What specific task does the system perform, in one sentence?", "Does any output inform a decision about a natural person (employee, candidate, or client)?", "Does it process biometric data, or infer emotions?", "Is a general-purpose AI model used, and if so which one?"],
 "confidence": "low"}
</answer>
</example>

<example>
<description>
SentinelPay. Screens incoming subscription and redemption instructions and
scores each investor's transaction pattern for money-laundering and payment
fraud indicators, raising alerts to the financial crime team for investigation.
Vendor-hosted, used as supplied.
</description>
<answer>
{"system_name": "SentinelPay",
 "provider_name": "SentinelPay",
 "system_purpose": "Scores investor transaction patterns for money-laundering and payment fraud indicators and raises alerts for human investigation.",
 "act_applies": "applies",
 "exclusion_ground": "none",
 "our_role": "deployer",
 "art25_trigger": "none",
 "risk_tier": "minimal_risk",
 "annex_iii_derogation": "none",
 "performs_profiling": true,
 "is_gpai": false,
 "gpai_note": null,
 "legal_basis": ["Annex III 5(b)"],
 "rationale": "The nearest Annex III entry is point 5(b), creditworthiness assessment and credit scoring of natural persons, which expressly excepts AI systems used for the purpose of detecting financial fraud. This system's purpose is fraud and money-laundering detection, so it falls within that exception and is not a high-risk Annex III system. The exception is written into the Annex III entry itself, so this is not an Article 6(3) derogation and no Article 6(4) documentation duty arises. It does profile natural persons, but profiling only forces the high-risk outcome for a system that is within Annex III in the first place.",
 "gaps": ["Is any output of this system used to assess an investor's creditworthiness, or to price or refuse a product for them? That would take it out of the fraud exception and into Annex III 5(b).", "Does an alert ever block a transaction automatically, without human review?"],
 "confidence": "medium"}
</answer>
</example>

<example>
<description>
InterviewScribe. Transcribes recorded interview calls verbatim and places each
passage under the competency heading on our interview form that the question
belonged to, so the hiring manager can write up their assessment faster. It
does not summarise, paraphrase, omit or highlight anything, and produces no
score, ranking, recommendation or characterisation of the candidate; the
manager reads the full transcript and writes the assessment themselves. The
vendor states it runs on a general-purpose speech-to-text and language model,
used as supplied. We buy it as a subscription.
</description>
<answer>
{"system_name": "InterviewScribe",
 "provider_name": "InterviewScribe",
 "system_purpose": "Transcribes interview recordings verbatim and groups the text under competency headings for the hiring manager to write up their own assessment.",
 "act_applies": "applies",
 "exclusion_ground": "none",
 "our_role": "deployer",
 "art25_trigger": "none",
 "risk_tier": "minimal_risk",
 "annex_iii_derogation": "preparatory_task",
 "performs_profiling": false,
 "is_gpai": true,
 "gpai_note": "Vendor states a general-purpose speech-to-text and language model is used, as supplied.",
 "legal_basis": ["Annex III 4(a)", "Article 6(3)(d)"],
 "rationale": "The system is used within a recruitment process, so Annex III point 4(a) is engaged; being used in recruitment is not by itself enough to make it high-risk, nor is being a transcriber enough to keep it out. On the facts stated — verbatim transcription, grouping by the question asked, no summary, omission or emphasis, and no evaluation of the candidate's traits — it performs a preparatory task to the assessment rather than the assessment itself, does not materially influence the outcome of the decision, and poses no significant risk to fundamental rights, so the Article 6(3) derogation applies on limb (d). It does not evaluate personal aspects of a natural person, so it does not perform profiling and the override in the final subparagraph of Article 6(3) is not triggered. Assessed separately, Article 50 is not engaged: the system does not interact with natural persons (it processes a recording after the interview), and its output reproduces what was said rather than generating synthetic content. Hence minimal_risk. The conclusion depends on those stated facts; if any of them fails, the derogation falls away.",
 "gaps": ["Can the vendor confirm the transcript is complete and unedited — no summarisation, paraphrase, omission or highlighting? Any of those could steer the assessment and would defeat the preparatory-task limb; summarising would also engage Article 50(2).", "Does the tool ever infer or label anything about the candidate — sentiment, confidence, communication skill? That would be evaluation, and profiling.", "Has the vendor documented its own Article 6(3) assessment under Article 6(4) and registered under Article 49(2)?"],
 "confidence": "medium"}
</answer>
</example>
"""

SYSTEM_PROMPT = f"""You classify AI systems under Regulation (EU) 2024/1689, the EU AI Act, as consolidated on 27 July 2026 (i.e. as amended by Regulation (EU) 2026/1744, the Digital Omnibus on AI), for a Luxembourg management company (ManCo) building its AI system inventory.

Answer the gates in this order. Each one can change or end the analysis, and answering them out of order is the main source of wrong classifications.

GATE 1 — Does the Act apply at all? (Article 2)
Set act_applies to 'excluded' only where an Article 2 exclusion clearly applies: exclusive military, defence or national security use; third-country public authorities in law-enforcement or judicial cooperation; a system developed and put into service for the SOLE purpose of scientific research and development; research, testing or development activity not yet placed on the market or put into service; or purely personal non-professional use by a natural person. Use 'unclear' where the description genuinely does not settle it. Otherwise 'applies'. A commercial procurement or an internal build by a firm established in the EU is 'applies'.
Note the difference from insufficient_information: 'excluded' means the Act does not reach this system. insufficient_information means we cannot tell what the system does. They are different findings and live in different fields.

GATE 2 — What role does the description state? (Article 3)
our_role is 'deployer' when we buy or use a third-party system, 'provider' when we build it or place it on the market under our own name, 'importer' or 'distributor' where that fits, 'unclear' when the description does not say. Do NOT apply Article 25 here.

GATE 3 — Does Article 25 escalate that role?
art25_trigger is not 'none' only where we have put our name or trademark on a HIGH-RISK system already on the market, substantially modified a HIGH-RISK system so that it remains high-risk, or changed the intended purpose of a system so that it BECOMES high-risk. All three are tied to the high-risk path. Re-badging or configuring a minimal-risk tool is 'none'. Use 'unclear' where the description hints at a modification but does not say enough.

GATE 4 — Which tier? Work down and stop at the first that applies.
1. prohibited — an Article 5 practice: emotion inference in the workplace or education institutions (Art. 5(1)(f)), social scoring, untargeted scraping of facial images, biometric categorisation inferring sensitive attributes, manipulative or exploitative techniques. Two further prohibitions, on non-consensual intimate imagery and on child sexual abuse material (Art. 5(1)(ba) and (bb)), were added by the Digital Omnibus and apply from 2 December 2026 — classify such a system as prohibited and say in the rationale that the prohibition applies from that date.
2. high_risk — a use listed in Annex III, or a safety component of a product under Annex I. The Annex III cases that arise in a ManCo are: recruitment and candidate evaluation (4(a)); decisions on promotion, termination, task allocation and monitoring of workers (4(b)); creditworthiness assessment or credit scoring of natural persons (5(b)); risk assessment and pricing in life and health insurance (5(c)); biometric identification (1).
3. limited_risk — Article 50 transparency duties apply: systems that interact directly with people, generate synthetic text, image, audio or video, or perform emotion recognition or biometric categorisation outside the prohibited cases.
4. minimal_risk — everything else.
5. insufficient_information — the description does not establish what the system does, who it affects, or our role.

GATE 5 — If, and only if, the system falls within an Annex III use: does Article 6(3) lift it back out?
An Annex III system is NOT high-risk where it does not pose a significant risk of harm to the health, safety or fundamental rights of natural persons, including by not materially influencing the outcome of decision making, AND at least one of these limbs genuinely describes it:
  (a) narrow_procedural_task — it performs a narrow procedural task;
  (b) improves_result_of_prior_human_activity — it improves the result of a previously completed human activity;
  (c) detects_decision_patterns_without_replacing_human_assessment — it detects decision-making patterns or deviations from prior patterns and is not meant to replace or influence the previously completed human assessment, without proper human review;
  (d) preparatory_task — it performs a preparatory task to an assessment relevant to an Annex III use case.
Where a limb applies, set annex_iii_derogation to that limb and set risk_tier to the tier that results — normally minimal_risk. Cite both the Annex III point and the Article 6(3) limb in legal_basis. Where none applies, annex_iii_derogation is 'none'.

GATE 6 — The profiling override.
Set performs_profiling true where the system performs profiling of natural persons: automated evaluation of personal aspects of a person, such as performance at work, economic situation, health, reliability, behaviour, location, interests or preferences. An Annex III system that performs profiling is ALWAYS high-risk, whatever limb of Article 6(3) might otherwise fit. Check this last, and let it override Gate 5.

Four things to hold on to, because they are where this goes wrong:

- Most AI in fund management is minimal risk. A system is not high-risk because it is important, expensive, client-facing, or regulated under another regime. DORA criticality, outsourcing materiality and AI Act tiering are different axes. Do not let the surrounding financial-services language pull a tool toward high_risk.
- The genuinely high-risk cases in a ManCo are usually about people, not portfolios: recruitment, HR, worker monitoring, and where the group does it, credit and insurance decisions on natural persons.
- Annex III 5(b) covers creditworthiness assessment and credit scoring of natural persons "with the exception of AI systems used for the purpose of detecting financial fraud". Fraud, AML and transaction-monitoring systems that score natural persons therefore fall OUTSIDE Annex III 5(b). That is a carve-out written into the Annex entry, not an Article 6(3) derogation: annex_iii_derogation stays 'none' and no Article 6(4) duty arises.
- A carve-out and a derogation both end in "not high-risk" and are different mechanisms. Keep them apart: a carve-out means the system was never in Annex III; a derogation means it is in Annex III and Article 6(3) lifts it out, which creates a documentation duty of its own under Article 6(4).

Rules for the answer:

- Classify only what the description supports. Where a fact is missing, put it in gaps as a question to the vendor rather than assuming it.
- Cite in legal_basis only the provisions the description actually supports, including a provision relied on to EXCLUDE the system (an Annex III point subject to a carve-out, or an Article 6(3) limb). An empty list is better than a plausible citation you cannot justify from the text.
- Prefer insufficient_information over a guess. An honest gap list is more useful to a compliance officer than a confident tier that cannot be defended.
- Article 3(1) first. If the description does not state, or clearly imply, that the system learns from data, predicts, infers or generates content — a rules engine, threshold monitor, reconciliation or reporting tool described only by its features is NOT established as an AI system — then set act_applies to "unclear", risk_tier to "insufficient_information" and confidence to "low", and make the first gap the question whether the product uses any machine-learned model at all. Do not assess the risk of a system whose existence as an AI system the text has not established.
- is_gpai is an independent flag. A general-purpose model can sit under a minimal-risk or a high-risk system.

Worked examples:
{FEW_SHOT}
""".strip()


# The system prompt is one cached block. It is built once at import and reused
# byte for byte on every call, which is the condition for a cache hit — a
# prompt assembled per call, even to the same string, is fine, but assembling
# it here makes it obvious that nothing per-description can leak into it.
#
# The description travels in the USER message instead. That is not a style
# choice: anything placed before the cache breakpoint changes the cached prefix
# and misses the cache on every row.
SYSTEM_BLOCKS = cached_system(SYSTEM_PROMPT)


class DescriptionTooLongError(ValueError):
    """The description exceeds MAX_DESCRIPTION_CHARS.

    A subclass of ValueError so existing `except ValueError` call sites still
    catch it, but distinguishable where a caller wants to say something more
    useful than "bad input" — the API returns a different message for it, and
    the UI can tell the user how much to cut.
    """

    def __init__(self, length: int, limit: int = MAX_DESCRIPTION_CHARS) -> None:
        super().__init__(
            f"Description is {length:,} characters; the limit is {limit:,}. "
            f"Paste the part that says what the system does, not the whole document."
        )
        self.length = length
        self.limit = limit


def validate_description(description: str) -> str:
    """Return the cleaned description, or raise before any money is spent.

    Both the API and the UI call this, so the two cannot drift into different
    ideas of what counts as valid input. Every rejection here is one that never
    opens a socket.

    Raises:
        ValueError: the description is empty or whitespace only.
        DescriptionTooLongError: past MAX_DESCRIPTION_CHARS.
    """
    description = (description or "").strip()
    if not description:
        raise ValueError("Nothing to classify: the description is empty.")
    if len(description) > MAX_DESCRIPTION_CHARS:
        raise DescriptionTooLongError(len(description))
    return description


def classify_with_meta(
    description: str,
    *,
    model: str = MODEL,
    max_attempts: int = 3,
    client: Anthropic | None = None,
) -> tuple[Classification, StructuredResult]:
    """Classify one description and also return the wrapper's result.

    The second value carries usage, attempts and stop_reason — what an eval,
    a cost table or the UI's cost line needs, and a caller that only wants the
    record does not.

    Raises on empty or over-long input rather than paying for a call that
    cannot produce anything useful — the cheapest failure is the one that never
    leaves the process.

    `client` is injectable so the edge-case tests can drive truncation and
    refusal paths deterministically, offline, with no API key.
    """
    description = validate_description(description)

    result = call_schema(
        ModelVerdict,
        prompt=(
            "Classify the following vendor or system description.\n\n"
            f"<description>\n{description}\n</description>"
        ),
        system=SYSTEM_BLOCKS,
        model=model,
        max_attempts=max_attempts,
        client=client,
    )
    return Classification.from_verdict(result.data), result


def classify(
    description: str,
    *,
    model: str = MODEL,
    max_attempts: int = 3,
    client: Anthropic | None = None,
) -> Classification:
    """Classify one vendor or system description. See classify_with_meta."""
    record, _ = classify_with_meta(
        description, model=model, max_attempts=max_attempts, client=client
    )
    return record


def main() -> None:
    # Read from argv, or from stdin when piped — a description with newlines is
    # much easier to pipe in than to quote on a command line.
    text = " ".join(sys.argv[1:]).strip() or (sys.stdin.read() if not sys.stdin.isatty() else "")
    if not text:
        raise SystemExit(
            'Usage: python -m src.aiact.classify "description"\n'
            "   or: cat description.txt | python -m src.aiact.classify"
        )

    # Imported here rather than at module scope: costlog is for callers that
    # want a cost line, and importing it at the top would make the core depend
    # on it for every consumer that does not.
    import time

    from toolkit.costlog import format_cost, price

    started = time.perf_counter()
    try:
        record, result = classify_with_meta(text)
    except ValueError as exc:  # empty or over-long — nothing was spent
        raise SystemExit(str(exc)) from exc
    except SchemaRetryError as exc:
        # The validation detail is kept off the exception's message because
        # the adapters must never show it. Here the text is your own and you
        # are debugging, so it goes to stderr — this is the one place it should.
        raise SystemExit(f"{exc}\n\n{exc.last_error}") from exc
    elapsed = time.perf_counter() - started

    # Article 50(2): the CLI record carries ai_generated like the API and the
    # UI export do, so all three adapters agree. First key, as in main.py.
    print(json.dumps({"ai_generated": True, **record.model_dump(mode="json")}, indent=2))
    # stderr, so `python -m src.aiact.classify ... > row.json` still writes
    # clean JSON to the file while you watch the cost in the terminal.
    print(
        f"\n{result.model} · {elapsed:.1f}s · attempts={result.attempts} · "
        f"{format_cost(price(result.usage, result.model))}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
