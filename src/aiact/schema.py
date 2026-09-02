"""schema.py — the output contract for the EU AI Act classifier.

WHAT IT DOES
    Defines what a classification *is*: the fields, the closed sets of values
    they may take, and which of them the model is allowed to decide.

WHY IT EXISTS
    This class is sent to the API as a JSON Schema and constrains generation,
    and it validates what comes back. One definition, both ends, so they cannot
    drift apart. Adding a field here changes the request and the check together.

    The split into two classes is the important part:
        ModelVerdict   - what the model is asked to produce
        Classification - the verdict plus the fields derived in Python
    Obligations and the effective role are NOT in ModelVerdict. Once the inputs
    are fixed, both are lookups in the regulation, and a dict cannot get them
    subtly wrong the way a model can. See obligations.py.

HOW TO USE IT
    from src.aiact.schema import ModelVerdict, Classification
    verdict = call_schema(ModelVerdict, prompt=...)      # model fills this
    record  = Classification.from_verdict(verdict.data)  # Python fills the rest

THE ORDER OF THE QUESTIONS IS THE POINT (added 2026-09-02)
    The Act is answered as a sequence of gates, not as one judgement, and the
    schema now mirrors that order:

        1. Does the Act apply at all?          Article 2      -> act_applies
        2. What is our stated role?            Article 3      -> our_role
        3. Has anything escalated that role?   Article 25     -> art25_trigger
        4. Which tier?                         Articles 5, 6  -> risk_tier
        5. If Annex III, is it derogated?      Article 6(3)   -> annex_iii_derogation
        6. ...unless it profiles people        Article 6(3)   -> performs_profiling

    Every one of those gates was missing before, and each of them turns a
    confident wrong answer into a correct one in cases a ManCo actually meets.
    Verified against the consolidated text at 27.07.2026; see
    notes/day2-act-review.md.

A CONSTRAINT WORTH KNOWING (verified in the installed SDK, 2026-08-31)
    anthropic/lib/_parse/_transform.py strips `minimum`, `maximum`, `minLength`,
    `maxLength` and `pattern` out of the schema and appends them to the field's
    description as plain text. They become a hint, not a rule. `enum` is in the
    supported subset and genuinely is enforced — which is why every new field
    below is an enum or a bool, never a bounded number.
"""
from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, Field

# Bumped whenever the tier rules, the obligations table, or the statutory dates
# change. It is stamped on every record so a row can be told apart from a row
# produced under different rules.
#
# v2 names the amending act explicitly: the AI Act as consolidated on
# 27.07.2026, i.e. Regulation (EU) 2024/1689 as amended by Regulation (EU)
# 2026/1744 (Digital Omnibus on AI, in force 27 July 2026).
RULESET_VERSION = "v2-2026-09-02-reg-2024-1689-consolidated-20260727"


class Applicability(str, Enum):
    """Article 2 — does the Regulation apply to this system at all?

    Asked *before* the tier, because in the Act it is a threshold question and
    not a degree of risk. Without this field an excluded system came back
    `minimal_risk`, which is a different and stronger claim than "the Act does
    not apply to this".
    """

    APPLIES = "applies"
    EXCLUDED = "excluded"
    UNCLEAR = "unclear"


class ExclusionGround(str, Enum):
    """Which Article 2 exclusion, when act_applies is 'excluded'.

    SCIENTIFIC_RD and PRE_MARKET_RD are the two that actually arise in a ManCo:
    an internal proof of concept may be out of scope entirely.
    """

    MILITARY_DEFENCE_NATIONAL_SECURITY = "military_defence_national_security"
    THIRD_COUNTRY_AUTHORITY_COOPERATION = "third_country_authority_cooperation"
    SCIENTIFIC_RD = "scientific_research_and_development"
    PRE_MARKET_RD = "research_testing_development_not_yet_placed_on_market"
    PERSONAL_NON_PROFESSIONAL = "personal_non_professional_activity"
    NONE = "none"


class Role(str, Enum):
    """Our organisation's role in relation to the system.

    The field that stops the obligations list from being fiction: the same
    system, at the same tier, carries a completely different obligation set for
    a provider than for a deployer.

    `UNCLEAR` is a real answer, not a failure — plenty of descriptions simply
    do not say, and pretending otherwise is how a wrong obligation list gets
    produced with a straight face.
    """

    PROVIDER = "provider"
    DEPLOYER = "deployer"
    IMPORTER = "importer"
    DISTRIBUTOR = "distributor"
    UNCLEAR = "unclear"


class Art25Trigger(str, Enum):
    """Article 25 — responsibilities along the AI value chain.

    A distributor, importer, deployer or other third party becomes the provider
    — and inherits the Article 16 obligations instead of Article 26 — in three
    circumstances. Read the scope carefully, because it is narrower than it
    first looks and getting it wrong in the other direction is its own error:

      (a) they put their name or trademark on a HIGH-RISK system already placed
          on the market, without prejudice to contractual arrangements
          allocating the obligations otherwise;
      (b) they make a substantial modification to a HIGH-RISK system already on
          the market such that it REMAINS high-risk under Article 6;
      (c) they modify the intended purpose of a system NOT classified as
          high-risk such that it BECOMES high-risk under Article 6.

    All three are tied to the high-risk path. White-labelling a minimal-risk
    vendor tool does NOT make us its provider under Article 25(1).

    Article 25(2): where escalation occurs, the initial provider stops being the
    provider of that system and owes the new provider cooperation, information
    and technical access. That is a contract point and a good gaps question.
    """

    NAME_OR_TRADEMARK = "name_or_trademark_on_high_risk_system"
    SUBSTANTIAL_MODIFICATION = "substantial_modification_of_high_risk_system"
    PURPOSE_CHANGE_TO_HIGH_RISK = "purpose_change_making_system_high_risk"
    NONE = "none"
    UNCLEAR = "unclear"


class AnnexIIIDerogation(str, Enum):
    """Article 6(3) — the four limbs, verbatim in substance.

    An Annex III system is NOT high-risk where it does not pose a significant
    risk of harm to health, safety or fundamental rights, including by not
    materially influencing the outcome of decision making, and any one of these
    conditions is met.

    This is the most important false-positive control in the Act. Without it the
    ladder reads "Annex III -> high risk, full stop", which over-calls exactly
    the cases a ManCo meets most often.

    Claiming it is not free: Article 6(4) requires a provider who considers an
    Annex III system not high-risk to document that assessment before placing
    the system on the market, and subjects them to the Article 49(2)
    registration obligation. The derogation is a filing, not an exit.
    """

    NARROW_PROCEDURAL_TASK = "narrow_procedural_task"
    IMPROVES_PRIOR_HUMAN_ACTIVITY = "improves_result_of_prior_human_activity"
    DETECTS_DECISION_PATTERNS = "detects_decision_patterns_without_replacing_human_assessment"
    PREPARATORY_TASK = "preparatory_task"
    NONE = "none"


class RiskTier(str, Enum):
    """Four legal tiers plus one honest one.

    INSUFFICIENT_INFORMATION is not a tier in the regulation and does not claim
    to be. It is the answer "this description does not let anyone classify
    this", and it exists as a tier value rather than as a null so that every
    consumer of the record has exactly one code path, and so that refusals are
    countable in the eval.

    Note it is NOT the same as act_applies='excluded'. "We cannot tell" and
    "the Act does not apply" are different findings and are recorded in
    different fields.
    """

    PROHIBITED = "prohibited"
    HIGH_RISK = "high_risk"
    LIMITED_RISK = "limited_risk"
    MINIMAL_RISK = "minimal_risk"
    INSUFFICIENT_INFORMATION = "insufficient_information"


class Confidence(str, Enum):
    """Three levels, deliberately not a number.

    A model reporting 0.87 is reporting a figure that was never calibrated
    against anything. Three levels can be defended to a risk committee and can
    be checked against hand labels on Day 13.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ModelVerdict(BaseModel):
    """Exactly what the model is asked to decide — nothing derivable.

    Every field is required. A nullable field (`provider_name`, `gpai_note`) is
    still required: the model must explicitly say null rather than omit it,
    which turns "didn't know" into a visible answer instead of a missing key.
    """

    system_name: str = Field(
        description="Name of the AI system or tool as given in the description. "
        "If unnamed, a short descriptive label."
    )
    provider_name: str | None = Field(
        description="The vendor or developer. Null if the description does not name one."
    )
    system_purpose: str = Field(
        description="One sentence: what the system does and what it is used for."
    )

    # --- Gate 1: does the Act apply at all? (Article 2) ---
    act_applies: Applicability = Field(
        description="Article 2. 'excluded' only where an Article 2 exclusion "
        "clearly applies — military/defence/national security, third-country "
        "authorities in law-enforcement cooperation, systems developed and put "
        "into service for the sole purpose of scientific research and "
        "development, research/testing/development activity not yet placed on "
        "the market or put into service, or purely personal non-professional "
        "use. 'unclear' when the description does not settle it. Otherwise "
        "'applies'."
    )
    exclusion_ground: ExclusionGround = Field(
        description="Which Article 2 exclusion applies. 'none' unless "
        "act_applies is 'excluded'."
    )

    # --- Gate 2 and 3: role, and whether Article 25 escalates it ---
    our_role: Role = Field(
        description="Our organisation's role AS THE DESCRIPTION STATES IT, "
        "before any Article 25 escalation. 'deployer' when we buy or use a "
        "third-party system, 'provider' when we develop it or place it on the "
        "market under our own name, 'unclear' when the description does not "
        "establish it. Do not apply Article 25 here — that is the next field."
    )
    art25_trigger: Art25Trigger = Field(
        description="Article 25. Have we put our name or trademark on a "
        "high-risk system, substantially modified a high-risk system so that it "
        "remains high-risk, or changed the intended purpose of a system so that "
        "it becomes high-risk? All three are tied to the high-risk path: "
        "white-labelling a minimal-risk tool is 'none'. Use 'unclear' only when "
        "the description suggests a modification but does not say enough."
    )

    # --- Gate 4, 5 and 6: tier, derogation, profiling override ---
    risk_tier: RiskTier = Field(
        description="Work down the ladder and stop at the first that applies: "
        "prohibited (Article 5) > high_risk (Annex III or Annex I) > "
        "limited_risk (Article 50 transparency duties) > minimal_risk. Use "
        "insufficient_information when the description does not establish the "
        "use, the persons affected, or our role. Apply the Article 6(3) "
        "derogation BEFORE settling on high_risk, and the profiling override "
        "after it. Where act_applies is 'excluded', still give the tier that "
        "would apply on the merits if you can tell — the record's obligations "
        "will reflect the exclusion."
    )
    annex_iii_derogation: AnnexIIIDerogation = Field(
        description="Article 6(3). Only meaningful for a system that falls "
        "within an Annex III use. Choose a limb only where the system does not "
        "pose a significant risk of harm to health, safety or fundamental "
        "rights, including by not materially influencing the outcome of "
        "decision making, AND the limb genuinely describes it. 'none' "
        "otherwise, and 'none' for any system that is not Annex III."
    )
    performs_profiling: bool = Field(
        description="Article 6(3), final subparagraph: an Annex III system "
        "ALWAYS remains high-risk where it performs profiling of natural "
        "persons — automated evaluation of personal aspects of a person, such "
        "as performance at work, economic situation, reliability, behaviour, "
        "interests or preferences. True where the system does that. This "
        "overrides any derogation limb."
    )

    is_gpai: bool = Field(
        description="True if a general-purpose AI model (a large language or "
        "multimodal model) is involved. This is an orthogonal flag, not a tier: "
        "a GPAI model can sit under a minimal-risk or a high-risk system."
    )
    gpai_note: str | None = Field(
        description="If is_gpai, one line on which model and whether we use it "
        "as supplied or modify it. Null otherwise."
    )

    legal_basis: list[str] = Field(
        description="Specific citations supporting the tier, e.g. "
        "['Annex III 4(a)'] or ['Article 5(1)(f)'] or ['Article 50(1)']. Also "
        "cite a provision relied on to EXCLUDE the system — an Annex III point "
        "subject to a carve-out, or the Article 6(3) limb claimed, e.g. "
        "['Annex III 4(a)', 'Article 6(3)(d)']. Empty list where nothing "
        "specific is engaged at all. Cite only what the description supports."
    )
    rationale: str = Field(
        description="Two or three sentences explaining the tier, written for a "
        "compliance officer. Reference what the description does and does not "
        "say. Where a derogation or exclusion is claimed, say why it fits."
    )
    gaps: list[str] = Field(
        description="Facts the description failed to establish, each phrased as "
        "a question to put back to the vendor. Empty only when nothing material "
        "is missing. On insufficient_information this list is the main output."
    )
    confidence: Confidence = Field(
        description="high = the description clearly establishes use, persons "
        "affected and role. medium = the tier is clear but some detail is "
        "assumed. low = material facts are missing or the case is genuinely "
        "borderline."
    )


class Classification(ModelVerdict):
    """A verdict plus the fields Python derives. This is the inventory row.

    Inheriting from ModelVerdict rather than repeating its fields means the
    contract with the model and the contract with the rest of the app cannot
    silently diverge.
    """

    effective_role: Role
    obligations: list[str]
    classified_at: date
    ruleset_version: str

    @staticmethod
    def derive_effective_role(
        our_role: Role, art25_trigger: Art25Trigger, risk_tier: RiskTier
    ) -> Role:
        """Apply Article 25(1) to the stated role.

        Deliberately narrow, because Article 25(1) is narrow. All three triggers
        concern high-risk systems, so escalation only happens on the high-risk
        path — reading it more broadly would produce the mirror-image error of
        the one it exists to fix.

        The asked role is kept in `our_role` and never overwritten: the delta
        between the two is auditable, and Day 13 can measure whether the model
        spotted the escalation separately from whether it got the role right.
        """
        escalating = {
            Art25Trigger.NAME_OR_TRADEMARK,
            Art25Trigger.SUBSTANTIAL_MODIFICATION,
            Art25Trigger.PURPOSE_CHANGE_TO_HIGH_RISK,
        }
        if (
            risk_tier is RiskTier.HIGH_RISK
            and art25_trigger in escalating
            and our_role in (Role.DEPLOYER, Role.IMPORTER, Role.DISTRIBUTOR)
        ):
            return Role.PROVIDER
        return our_role

    @classmethod
    def from_verdict(cls, verdict: ModelVerdict, *, today: date | None = None) -> "Classification":
        """Build the full record. Obligations are looked up, never generated."""
        from src.aiact.obligations import obligations_for  # local import: avoids a cycle

        effective_role = cls.derive_effective_role(
            verdict.our_role, verdict.art25_trigger, verdict.risk_tier
        )
        return cls(
            **verdict.model_dump(),
            effective_role=effective_role,
            obligations=obligations_for(
                verdict.risk_tier,
                effective_role,
                verdict.is_gpai,
                verdict.legal_basis,
                act_applies=verdict.act_applies,
                exclusion_ground=verdict.exclusion_ground,
                derogation=verdict.annex_iii_derogation,
                performs_profiling=verdict.performs_profiling,
                art25_trigger=verdict.art25_trigger,
                stated_role=verdict.our_role,
            ),
            classified_at=today or date.today(),
            ruleset_version=RULESET_VERSION,
        )
