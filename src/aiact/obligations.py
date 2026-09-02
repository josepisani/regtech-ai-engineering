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
    SETTLED      : the Omnibus is Regulation (EU) 2026/1744 of 8 July 2026,
                   OJ L series 24 July 2026, in force 27 July 2026. Verified on
                   EUR-Lex 2026-09-02. Work against the consolidated text:
                   eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:02024R1689-20260727
"""
from __future__ import annotations

from src.aiact.schema import (
    AnnexIIIDerogation,
    Applicability,
    Art25Trigger,
    ExclusionGround,
    RiskTier,
    Role,
)

# Art. 4(1) binds PROVIDERS AND DEPLOYERS, at every tier — not importers or
# distributors who are neither. obligations_for() gates it on the role.
UNIVERSAL = [
    "Art. 4 — take measures to support the development of AI literacy among "
    "staff and others operating or using the system on our behalf, "
    "proportionate to their technical knowledge, experience, education and "
    "training and to the context of use. The Article does not require any "
    "specific level of AI literacy to be guaranteed for any individual. "
    "Binds providers and deployers. In force since 2 February 2025.",
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
    "No mandatory obligations under the AI Act at this tier, beyond any AI "
    "literacy duty listed above.",
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


# --- Article 2: the Act does not apply at all -------------------------------
# Asked before the tier, because in the Act it is a threshold question. An
# excluded system used to come back minimal_risk, which is a different and
# stronger claim than "the Act does not apply to this".
_EXCLUSION_TEXT = {
    ExclusionGround.MILITARY_DEFENCE_NATIONAL_SECURITY: (
        "Art. 2 — outside the scope of the AI Act: the system is exclusively "
        "developed and used for military, defence or national security purposes."
    ),
    ExclusionGround.THIRD_COUNTRY_AUTHORITY_COOPERATION: (
        "Art. 2 — outside the scope of the AI Act: use by third-country public "
        "authorities or international organisations in law-enforcement and "
        "judicial cooperation."
    ),
    ExclusionGround.SCIENTIFIC_RD: (
        "Art. 2(6) — outside the scope of the AI Act: specifically developed "
        "and put into service for the sole purpose of scientific research and "
        "development. The exclusion is narrow: it fails the moment the system "
        "is used in production, so record the date it stops being research."
    ),
    ExclusionGround.PRE_MARKET_RD: (
        "Art. 2 — outside the scope of the AI Act: research, testing or "
        "development activity, not yet placed on the market or put into "
        "service. This is a stage, not a property. Re-classify before go-live."
    ),
    ExclusionGround.PERSONAL_NON_PROFESSIONAL: (
        "Art. 2 — outside the scope of the AI Act: use by a natural person in "
        "the course of a purely personal non-professional activity. Rarely the "
        "right answer for anything in a firm's inventory."
    ),
}

_EXCLUDED_TAIL = [
    "No AI Act obligations follow while the exclusion holds. Keep the row in "
    "the inventory: an exclusion is a fact about today's use, not about the "
    "system, and a change of use brings it back into scope.",
]

_SCOPE_UNCLEAR = [
    "Whether the AI Act applies to this system could not be established from "
    "the description. Settle Art. 2 scope before deriving any obligations — a "
    "system that is out of scope has none, and one that is in scope may have "
    "many.",
]

# --- Article 6(4): claiming the Annex III derogation is a filing ------------
# The derogation removes the high-risk obligations. It does not remove all of
# them: a provider who claims it takes on a documentation and registration duty
# of its own, and that duty is easy to miss precisely because the classification
# just came back "not high-risk".
_DEROGATION_PROVIDER = [
    "Art. 6(4) — document the assessment that this Annex III system is not "
    "high-risk BEFORE it is placed on the market or put into service, and "
    "produce that documentation to national competent authorities on request.",
    "Art. 49(2) — register the system in the EU database as an Annex III system "
    "considered not to be high-risk.",
]

_DEROGATION_DEPLOYER = [
    "The provider has claimed the Art. 6(3) derogation. The Art. 6(4) "
    "documentation and Art. 49(2) registration duties fall on them, not on us — "
    "but ask for the assessment: if it does not hold, the system is high-risk "
    "and our Art. 26 duties revive.",
]

_ART25_NOTE = [
    "Art. 25(1) — by putting our name on this system, substantially modifying "
    "it, or changing its intended purpose, we are the PROVIDER of it for the "
    "purposes of the Regulation, and carry the Art. 16 provider obligations "
    "rather than the Art. 26 deployer ones.",
    "Art. 25(2) — the original provider is no longer the provider of this "
    "system. Confirm in writing that they will supply the information and "
    "technical access we need to meet those obligations, in particular for "
    "conformity assessment.",
]


def obligations_for(
    tier: RiskTier,
    role: Role,
    is_gpai: bool,
    legal_basis: list[str] | None = None,
    *,
    act_applies: Applicability = Applicability.APPLIES,
    exclusion_ground: ExclusionGround = ExclusionGround.NONE,
    derogation: AnnexIIIDerogation = AnnexIIIDerogation.NONE,
    performs_profiling: bool = False,
    art25_trigger: Art25Trigger = Art25Trigger.NONE,
    stated_role: Role | None = None,
) -> list[str]:
    """Return the obligations for one classified system.

    `role` is the EFFECTIVE role — Article 25 already applied by
    Classification.derive_effective_role. `stated_role` is what the description
    said, and is used only to notice that an escalation happened so the record
    can say so.

    The gates are applied in the order the Act asks them, and each one can end
    the function:

        Article 2  scope        -> excluded, or unclear: stop
        Article 6(3)/(4)        -> derogation claimed: high-risk duties fall away,
                                   a documentation duty appears
        tier + role             -> the main table
        Article 25              -> a note explaining why the role changed

    Unknown role on a high-risk system does not fall back to a guess: it returns
    an explicit instruction to establish the role first, because the deployer
    list and the provider list are very different and picking the wrong one
    produces a document that looks complete and is wrong.
    """
    # --- Gate 1: does the Act apply? -------------------------------------
    if act_applies is Applicability.EXCLUDED:
        head = _EXCLUSION_TEXT.get(
            exclusion_ground,
            "Art. 2 — outside the scope of the AI Act. The exclusion ground was "
            "not identified; establish which one is relied on before relying on "
            "this record.",
        )
        return [head, *_EXCLUDED_TAIL]

    if act_applies is Applicability.UNCLEAR:
        return list(_SCOPE_UNCLEAR)

    if tier is RiskTier.INSUFFICIENT_INFORMATION:
        # No universal line either: the record makes no claim about the system.
        return list(_INSUFFICIENT)

    out: list[str] = []

    # --- Art. 4 applies to providers and deployers, not to everyone -------
    # (Art. 4(1): "Providers and deployers of AI systems shall take measures to
    # support the development of AI literacy...". An importer or distributor
    # that is neither is not caught by it.)
    if role in (Role.PROVIDER, Role.DEPLOYER, Role.UNCLEAR):
        out += UNIVERSAL

    # --- Gate 2: Article 6(3) derogation ---------------------------------
    # The profiling override is checked first: it defeats any limb.
    derogation_effective = (
        derogation is not AnnexIIIDerogation.NONE and not performs_profiling
    )
    if derogation is not AnnexIIIDerogation.NONE and performs_profiling:
        out.append(
            "Art. 6(3), final subparagraph — a derogation limb was identified, "
            "but an Annex III system that performs profiling of natural persons "
            "is ALWAYS high-risk. The derogation does not apply and the "
            "high-risk obligations below stand."
        )

    if derogation_effective:
        out.append(
            "Art. 6(3) — this Annex III system is not high-risk: it does not "
            "pose a significant risk of harm to health, safety or fundamental "
            f"rights, on the ground '{derogation.value}'."
        )
        if role is Role.PROVIDER:
            out += _DEROGATION_PROVIDER
        else:
            out += _DEROGATION_DEPLOYER
        out += _MINIMAL_RISK[1:]  # the inventory reminder, not the "no obligations" line
        if is_gpai:
            out += _GPAI_NOTE
        return out

    # --- Gate 3: the tier table ------------------------------------------
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

    # --- Gate 4: say why the role changed --------------------------------
    if (
        stated_role is not None
        and role is Role.PROVIDER
        and stated_role is not Role.PROVIDER
        and art25_trigger
        in (
            Art25Trigger.NAME_OR_TRADEMARK,
            Art25Trigger.SUBSTANTIAL_MODIFICATION,
            Art25Trigger.PURPOSE_CHANGE_TO_HIGH_RISK,
        )
    ):
        out += _ART25_NOTE
    elif art25_trigger is Art25Trigger.UNCLEAR and tier is RiskTier.HIGH_RISK:
        out.append(
            "The description suggests we may have renamed, modified or "
            "repurposed this system. If so, Art. 25(1) makes us its provider "
            "and the obligations above are the wrong list. Settle this first."
        )

    if is_gpai:
        out += _GPAI_NOTE

    return out
