"""examples.py — the descriptions the demo offers before it offers a text box.

WHY THIS FILE EXISTS
    Two reasons, and the second is the one that made it worth writing.

    1. A demo needs something to demo. Most people opening a portfolio link
       will not compose a vendor description; they will click something and
       look at the output. Making examples the default path means the tool
       shows what it does to everyone, not only to the few who type.

    2. It is the cheapest privacy control there is. A free text box on a public
       page invites someone to paste a CV, a client name or an incident report,
       and at that moment the operator is a GDPR controller of whatever arrived.
       Not storing it helps; not receiving it is better. Examples first, free
       text behind a deliberate choice, removes most of that traffic without
       removing the capability.

WHY THESE FOUR, AND NOT THE FIVE IN THE PROMPT
    None of these is a few-shot example from src/aiact/classify.py. Demoing a
    model on its own worked examples is a rigged demo, and an interviewer who
    reads the prompt will spot it in about a minute. These are unseen inputs,
    chosen so the four outcomes that are actually interesting each appear once:

        ShortlistPro  -> high_risk. The textbook Annex III 4(a) case.
        FraudLens     -> NOT high_risk. The Annex III 5(b) fraud carve-out, and
                         the most counter-intuitive answer the tool gives: it
                         scores natural persons, in a bank, and is still out.
        Aurora        -> insufficient_information, with the questions to ask.
                         This is the output a decision-tree tool cannot produce.
        ClientDesk    -> limited_risk. Article 50 transparency, nothing more.

DELIBERATELY HELD BACK
    A fifth example belongs here — a deterministic threshold-matching
    reconciliation engine, where the real question is "is this an AI system at
    all?" under Article 3(1). It is held back because the schema has no field
    for that question yet (notes/day3.md, pattern A), so the tool currently
    answers it confidently and wrongly. Add it the day the Article 3(1) gate
    lands; it will be the best example in the set, because getting that one
    right is what separates this from a keyword matcher.
"""
from __future__ import annotations

EXAMPLES: dict[str, str] = {
    "Recruitment screener (vendor SaaS)": (
        "ShortlistPro. Reads each applicant's CV against the role description and "
        "scores them from 1 to 100 on fit, then ranks the applicants so the hiring "
        "manager can start at the top. Used for first-round screening on all "
        "operations roles. Vendor-hosted in Frankfurt, used as supplied."
    ),
    "AML transaction monitoring": (
        "FraudLens. Monitors investor subscription and redemption activity and "
        "scores each investor's transaction pattern against typologies for money "
        "laundering and payment fraud, raising alerts to the financial crime team "
        "for investigation. Alerts are reviewed by an analyst before any action is "
        "taken. Vendor-hosted, used as supplied."
    ),
    "A vendor blurb that says nothing": (
        "Aurora is an AI-native platform that helps operations teams work smarter. "
        "It uses advanced machine learning to surface insights and drive efficiency "
        "across the middle office. Enterprise-grade, ISO 27001 certified, deployed "
        "by leading asset managers."
    ),
    "Client-facing assistant": (
        "ClientDesk. A chat assistant on our investor portal that answers questions "
        "about fund documentation, dealing deadlines and NAV publication times, "
        "drawing on our published prospectuses and factsheets. Investors type "
        "questions and it replies in natural language. Built in-house on a "
        "third-party large language model accessed through an API."
    ),
}
