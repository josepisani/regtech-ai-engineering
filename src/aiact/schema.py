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
    Obligations are NOT in ModelVerdict. Once tier and role are fixed, the
    obligations are a lookup in the regulation, and a dict cannot get it subtly
    wrong the way a model can. See obligations.py.

HOW TO USE IT
    from src.aiact.schema import ModelVerdict, Classification
    verdict = call_schema(ModelVerdict, prompt=...)      # model fills this
    record  = Classification.from_verdict(verdict.data)  # Python fills the rest

A CONSTRAINT WORTH KNOWING (verified in the installed SDK, 2026-08-31)
    anthropic/lib/_parse/_transform.py strips `minimum`, `maximum`, `minLength`,
    `maxLength` and `pattern` out of the schema and appends them to the field's
    description as plain text. They become a hint, not a rule. `enum` is in the
    supported subset and genuinely is enforced — which is why `confidence` is an
    enum of three levels and not a float with ge/le bounds. A float would have
    looked enforced and would not have been.
"""
from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, Field

# Bumped whenever the tier rules, the obligations table, or the statutory dates
# change. It is stamped on every record so a row can be told apart from a row
# produced under different rules — which matters because the AI Act timeline
# moved in 2026 and will move again.
RULESET_VERSION = "v1-2026-08-31-post-omnibus"


class Role(str, Enum):
    """Our organisation's role in relation to the system.

    The field that stops the obligations list from being fiction: the same
    system, at the same tier, carries a completely different obligation set for
    a provider than for a deployer. A ManCo buying a vendor tool is normally a
    deployer; one that fine-tunes a model and puts its own name on the result
    can become a provider.

    `UNCLEAR` is a real answer, not a failure — plenty of descriptions simply
    do not say, and pretending otherwise is how a wrong obligation list gets
    produced with a straight face.
    """

    PROVIDER = "provider"
    DEPLOYER = "deployer"
    IMPORTER = "importer"
    DISTRIBUTOR = "distributor"
    UNCLEAR = "unclear"


class RiskTier(str, Enum):
    """Four legal tiers plus one honest one.

    INSUFFICIENT_INFORMATION is not a tier in the regulation and does not claim
    to be. It is the answer "this description does not let anyone classify
    this", and it exists as a tier value rather than as a null so that every
    consumer of the record has exactly one code path, and so that refusals are
    countable in the eval instead of invisible.
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

    our_role: Role = Field(
        description="Our organisation's role in relation to this system. Use "
        "'deployer' when we buy or use a third-party system, 'provider' when we "
        "develop it or place it on the market under our own name, 'unclear' when "
        "the description does not establish it."
    )
    risk_tier: RiskTier = Field(
        description="Work down the ladder and stop at the first that applies: "
        "prohibited (Article 5) > high_risk (Annex III or Annex I) > limited_risk "
        "(Article 50 transparency duties) > minimal_risk. Use "
        "insufficient_information when the description does not establish the "
        "use, the persons affected, or our role."
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
        "['Annex III 4(a)'] or ['Article 5(1)(f)'] or ['Article 50(1)']. Empty "
        "list for minimal_risk or insufficient_information. Cite only what the "
        "description actually supports."
    )
    rationale: str = Field(
        description="Two or three sentences explaining the tier, written for a "
        "compliance officer. Reference what the description does and does not say."
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

    obligations: list[str]
    classified_at: date
    ruleset_version: str

    @classmethod
    def from_verdict(cls, verdict: ModelVerdict, *, today: date | None = None) -> "Classification":
        """Build the full record. Obligations are looked up, never generated."""
        from src.aiact.obligations import obligations_for  # local import: avoids a cycle

        return cls(
            **verdict.model_dump(),
            obligations=obligations_for(
                verdict.risk_tier,
                verdict.our_role,
                verdict.is_gpai,
                verdict.legal_basis,
            ),
            classified_at=today or date.today(),
            ruleset_version=RULESET_VERSION,
        )
