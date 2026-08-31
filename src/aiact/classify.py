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

from dotenv import load_dotenv

from src.aiact.schema import Classification, ModelVerdict
from toolkit.structured import call_schema

load_dotenv()

MODEL = "claude-haiku-4-5"

# The few-shot examples are chosen, not collected. One obvious case, one that
# looks high-risk and is not, and one that cannot be classified at all.
#
# The middle example is doing the most work. A model asked to classify anything
# in a financial firm drifts toward high_risk, because the surrounding language
# is full of risk, regulation and client money. Annex III is about a specific
# list of uses, mostly concerning decisions about people. An example that is
# important, regulated, expensive AND minimal-risk is the lever that corrects
# that drift.
#
# The third example teaches that "I cannot classify this" is a permitted answer.
# Without it, every example ends in a confident tier, and a confident tier is
# the pattern the model continues.
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
 "our_role": "deployer",
 "risk_tier": "high_risk",
 "is_gpai": false,
 "gpai_note": null,
 "legal_basis": ["Annex III 4(a)"],
 "rationale": "The system is used for recruitment and specifically to filter applications and evaluate candidates, which is the Annex III point 4(a) use case. We buy and use it rather than develop it, so we act as deployer. The scoring is applied to natural persons and affects access to employment.",
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
 "our_role": "provider",
 "risk_tier": "minimal_risk",
 "is_gpai": false,
 "gpai_note": null,
 "legal_basis": [],
 "rationale": "Anomaly detection on fund valuation data is not a listed Annex III use: it makes no decision about a natural person, performs no biometric or emotion processing, and is not a safety component of a regulated product. It is operationally critical and may be significant under other regimes, but criticality is not an AI Act tiering criterion. Built in-house, so we are the provider.",
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
 "our_role": "deployer",
 "risk_tier": "insufficient_information",
 "is_gpai": false,
 "gpai_note": null,
 "legal_basis": [],
 "rationale": "The description states a benefit rather than a function. Without knowing what the system does, what data it processes, and whether its outputs affect decisions about natural persons, no tier can be assigned. SOC 2 certification concerns information security controls and says nothing about AI Act classification.",
 "gaps": ["What specific task does the system perform, in one sentence?", "Does any output inform a decision about a natural person (employee, candidate, or client)?", "Does it process biometric data, or infer emotions?", "Is a general-purpose AI model used, and if so which one?"],
 "confidence": "low"}
</answer>
</example>
"""

SYSTEM_PROMPT = f"""You classify AI systems under Regulation (EU) 2024/1689, the EU AI Act, for a Luxembourg management company (ManCo) building its AI system inventory.

Work down this ladder and stop at the first tier that applies:

1. prohibited — an Article 5 practice. Includes emotion recognition in the workplace or in education (Art. 5(1)(f)), social scoring, untargeted scraping of facial images, biometric categorisation to infer sensitive attributes, and manipulative or exploitative techniques.
2. high_risk — a use listed in Annex III, or a safety component of a product under Annex I. The Annex III cases that arise in a ManCo are: recruitment and candidate evaluation (4(a)); decisions on promotion, termination, task allocation and monitoring of workers (4(b)); creditworthiness assessment of natural persons (5(b)); risk assessment and pricing in life and health insurance (5(c)); biometric identification (1).
3. limited_risk — Article 50 transparency duties apply. Systems that interact directly with people (chatbots), generate synthetic text, image, audio or video, or perform emotion recognition or biometric categorisation outside the prohibited cases.
4. minimal_risk — everything else.
5. insufficient_information — the description does not establish what the system does, who it affects, or our role.

Two things to hold on to, because they are where this goes wrong:

- Most AI in fund management is minimal risk. A system is not high-risk because it is important, expensive, client-facing, or regulated under another regime. DORA criticality, outsourcing materiality and AI Act tiering are different axes. Do not let the surrounding financial-services language pull a tool toward high_risk.
- The genuinely high-risk cases in a ManCo are usually about people, not portfolios: recruitment, HR, worker monitoring, and where the group does it, credit and insurance decisions on natural persons.

Rules for the answer:

- Classify only what the description supports. Where a fact is missing, put it in gaps as a question to the vendor rather than assuming it.
- Cite in legal_basis only the provisions the description actually supports. An empty list is better than a plausible citation you cannot justify from the text.
- Prefer insufficient_information over a guess. An honest gap list is more useful to a compliance officer than a confident tier that cannot be defended.
- our_role is 'deployer' when we buy or use a third-party system, 'provider' when we build it or place it on the market under our own name, 'unclear' when the description does not say.
- is_gpai is an independent flag. A general-purpose model can sit under a minimal-risk system.

Worked examples:
{FEW_SHOT}
""".strip()


def classify(description: str, *, model: str = MODEL, max_attempts: int = 3) -> Classification:
    """Classify one vendor or system description.

    Raises ValueError on empty input rather than paying for a call that cannot
    produce anything useful — the cheapest failure is the one that never leaves
    the process.
    """
    description = description.strip()
    if not description:
        raise ValueError("Nothing to classify: the description is empty.")

    result = call_schema(
        ModelVerdict,
        prompt=(
            "Classify the following vendor or system description.\n\n"
            f"<description>\n{description}\n</description>"
        ),
        system=SYSTEM_PROMPT,
        model=model,
        max_attempts=max_attempts,
    )
    return Classification.from_verdict(result.data)


def main() -> None:
    # Read from argv, or from stdin when piped — a description with newlines is
    # much easier to pipe in than to quote on a command line.
    text = " ".join(sys.argv[1:]).strip() or (sys.stdin.read() if not sys.stdin.isatty() else "")
    if not text:
        raise SystemExit(
            'Usage: python -m src.aiact.classify "description"\n'
            "   or: cat description.txt | python -m src.aiact.classify"
        )
    print(classify(text).model_dump_json(indent=2))


if __name__ == "__main__":
    main()
