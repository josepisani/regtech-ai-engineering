"""obligations.py — tier + role -> obligations, as a lookup, not a generation.

WHAT IT DOES
    Maps (risk_tier, our_role, is_gpai) to the list of AI Act obligations that
    follow, with article citations and the date each one starts to apply.

WHY IT EXISTS
    This is the part of the answer that must never be hallucinated. Once the
    tier and the role are decided, the obligations are a table in the
    regulation — fixed, checkable, and identical for every system in that cell.
    Asking a model to recite it costs money and adds a failure mode that a dict
    does not have. When someone asks "how do you stop it making things up", the
    answer for this field is: the model is not consulted.

    The trade is that this table is only as current as the person maintaining
    it. Hence RULESET_VERSION in schema.py, stamped on every record.

HOW TO USE IT
    from src.aiact.obligations import obligations_for
    obligations_for(RiskTier.HIGH_RISK, Role.DEPLOYER, is_gpai=False)

TIMELINE ENCODED HERE (post Digital Omnibus, verify before Day 4 ships)
    In force now : Art. 4 AI literacy and Art. 5 prohibitions (2 Feb 2025);
                   GPAI obligations, Ch. V (2 Aug 2025);
                   Art. 50 transparency (2 Aug 2026).
    Deferred     : Annex III high-risk -> 2 Dec 2027 (was 2 Aug 2026);
                   Annex I embedded high-risk -> 2 Aug 2028 (was 2 Aug 2027).
    OPEN ITEM    : sources disagree on whether the Omnibus is formally adopted
                   and published in the Official Journal. Check EUR-Lex and
                   record the answer in the README. Until then this module
                   states the post-Omnibus dates and says so on every record.
"""
from __future__ import annotations

from src.aiact.schema import RiskTier, Role

# Applies to everyone, every tier: the one obligation nobody escapes.
UNIVERSAL = [
    "Art. 4 — ensure staff who operate or are affected by the system have "
    "sufficient AI literacy. In force since 2 February 2025.",
]

_PROHIBITED = [
    "Art. 5 — do not place on the market, put into service, or use. In force "
    "since 2 February 2025.",
    "If the system is already in use, cease use and document the decision and "
    "the date.",
    "Escalate to the Conducting Officer and the board; this is a licence-risk "
    "item, not a project.",
]

_HIGH_RISK_DEPLOYER = [
    "Art. 26(1) — use the system in accordance with the provider's instructions "
    "for use.",
    "Art. 26(2) — assign human oversight to natural persons with the necessary "
    "competence, training and authority.",
    "Art. 26(4) — ensure input data is relevant and sufficiently representative "
    "for the intended purpose, to the extent we control the input data.",
    "Art. 26(5) — monitor operation; suspend use and inform the provider and the "
    "market surveillance authority where a risk or serious incident arises.",
    "Art. 26(6) — keep the automatically generated logs for at least six months.",
    "Art. 26(7) — inform workers' representatives and affected workers before "
    "putting the system into service in the workplace.",
    "Art. 26(11) — inform natural persons that they are subject to a decision "
    "taken with the system.",
    "Art. 27 — carry out a fundamental rights impact assessment if we are a "
    "public body, a private entity providing public services, or we use the "
    "system for creditworthiness assessment or life/health insurance pricing.",
    "Applies from 2 December 2027 for Annex III systems (deferred by the Digital "
    "Omnibus from 2 August 2026). Preparation is a 2027 project; it is not a "
    "reason to defer the inventory.",
]

_HIGH_RISK_PROVIDER = [
    "Art. 9 — establish and maintain a risk management system across the "
    "lifecycle.",
    "Art. 10 — data governance: training, validation and testing data must meet "
    "quality criteria.",
    "Art. 11 + Annex IV — draw up and keep technical documentation.",
    "Art. 12 — design for automatic record-keeping (logging).",
    "Art. 13 — provide instructions for use enabling deployers to comply.",
    "Art. 14 — design for effective human oversight.",
    "Art. 15 — appropriate accuracy, robustness and cybersecurity.",
    "Art. 17 — operate a quality management system.",
    "Art. 43, 47, 48 — conformity assessment, EU declaration of conformity, CE "
    "marking.",
    "Art. 49 — register the system in the EU database before placing on market.",
    "Art. 72, 73 — post-market monitoring and serious incident reporting.",
    "Applies from 2 December 2027 for Annex III systems (post-Omnibus).",
]

_HIGH_RISK_DISTRIBUTION = [
    "Art. 23/24 — verify the system bears CE marking, the provider has met its "
    "obligations, and instructions for use are supplied; do not make available "
    "if you have reason to believe it is non-conforming.",
    "Applies from 2 December 2027 for Annex III systems (post-Omnibus).",
]

# Article 50 does not attach per role alone: each paragraph is a different duty
# with a different addressee. Keying the lookup on (tier, role) only was wrong —
# it handed a chatbot deployer the deepfake and emotion-recognition duties, which
# is exactly the confidently-wrong obligation list this project exists to avoid.
# So the switch is the paragraph the classifier actually cited.
_ART50 = {
    "50(1)": {
        "provider": "Art. 50(1) — design and build so that persons are informed "
        "they are interacting with an AI system, unless it is obvious.",
        "deployer": "Art. 50(1) — the design duty falls on the provider, but "
        "confirm the disclosure is actually presented to our users and that the "
        "contract obliges the provider to maintain it.",
    },
    "50(2)": {
        "provider": "Art. 50(2) — mark synthetic audio, image, video or text "
        "output in a machine-readable format detectable as artificially "
        "generated. Grace period to 2 December 2026 for systems already on the "
        "market before 2 August 2026.",
        "deployer": "Art. 50(2) — the marking duty falls on the provider; "
        "confirm the vendor applies machine-readable marking to generated "
        "output.",
    },
    "50(3)": {
        "provider": "Art. 50(3) — build so that exposure to emotion recognition "
        "or biometric categorisation can be disclosed to the persons concerned.",
        "deployer": "Art. 50(3) — inform natural persons exposed to an emotion "
        "recognition or biometric categorisation system that it is in operation, "
        "and process personal data in line with the GDPR.",
    },
    "50(4)": {
        "provider": "Art. 50(4) — enable disclosure of artificially generated or "
        "manipulated image, audio, video or text output.",
        "deployer": "Art. 50(4) — disclose deepfake content, and disclose "
        "AI-generated text published to inform the public on matters of public "
        "interest.",
    },
}

_ART50_IN_FORCE = "Article 50 transparency duties are in force since 2 August 2026."

_ART50_UNIDENTIFIED = (
    "The classification did not cite a specific Article 50 paragraph, so the "
    "applicable transparency duty could not be narrowed. Establish which of "
    "50(1) interaction, 50(2) synthetic-content marking, 50(3) emotion or "
    "biometric categorisation, or 50(4) deepfake and public-interest text "
    "applies before relying on this record."
)

_MINIMAL_RISK = [
    "No mandatory obligations under the AI Act beyond Art. 4 AI literacy.",
    "Art. 95 — voluntary codes of conduct may be applied.",
    "Record the system in the inventory anyway: tiering is a point-in-time "
    "judgement and a change of use can change the tier.",
]

_GPAI_NOTE = [
    "Ch. V (Art. 53-55) — obligations fall on the provider of the "
    "general-purpose model, not on us as a downstream user. In force since "
    "2 August 2025.",
    "If we fine-tune a general-purpose model or place it on the market under our "
    "own name, we may become its provider and inherit those obligations — "
    "confirm before any fine-tuning project starts.",
]

_INSUFFICIENT = [
    "Obligations cannot be determined until the gaps in this record are closed. "
    "Send the gap questions to the vendor and re-classify on their answer.",
]


def obligations_for(
    tier: RiskTier,
    role: Role,
    is_gpai: bool,
    legal_basis: list[str] | None = None,
) -> list[str]:
    """Return the obligations for one (tier, role, gpai) cell.

    Unknown role on a high-risk system does not fall back to a guess: it returns
    an explicit instruction to establish the role first, because the deployer
    list and the provider list are very different and picking the wrong one
    produces a document that looks complete and is wrong.
    """
    if tier is RiskTier.INSUFFICIENT_INFORMATION:
        # No universal line either: the record makes no claim about the system.
        return list(_INSUFFICIENT)

    out: list[str] = list(UNIVERSAL)

    if tier is RiskTier.PROHIBITED:
        out += _PROHIBITED
    elif tier is RiskTier.HIGH_RISK:
        if role is Role.DEPLOYER:
            out += _HIGH_RISK_DEPLOYER
        elif role is Role.PROVIDER:
            out += _HIGH_RISK_PROVIDER
        elif role in (Role.IMPORTER, Role.DISTRIBUTOR):
            out += _HIGH_RISK_DISTRIBUTION
        else:
            out.append(
                "Role is unclear, and the high-risk obligations for a provider "
                "differ substantially from those for a deployer. Establish the "
                "role before deriving obligations."
            )
    elif tier is RiskTier.LIMITED_RISK:
        # 'unclear' role gets both sides rather than a guess: an over-long list
        # is an inconvenience, a wrong list is a compliance failure.
        sides = ("provider", "deployer") if role is Role.UNCLEAR else (
            "provider" if role is Role.PROVIDER else "deployer",
        )
        cited = [p for p in _ART50 if any(p in ref for ref in (legal_basis or []))]
        if cited:
            for para in cited:
                out += [_ART50[para][side] for side in sides]
            out.append(_ART50_IN_FORCE)
        else:
            out.append(_ART50_UNIDENTIFIED)
            out.append(_ART50_IN_FORCE)
    elif tier is RiskTier.MINIMAL_RISK:
        out += _MINIMAL_RISK

    if is_gpai:
        out += _GPAI_NOTE

    return out
