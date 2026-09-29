from typing import Literal

from pydantic import BaseModel, Field

# Confidence bands shown in the UI. Below REVIEW_THRESHOLD a clinician
# should double-check the triage priority before acting on it.
HIGH_CONFIDENCE = 0.80
REVIEW_THRESHOLD = 0.60


class TriageModelOutput(BaseModel):
    """The four fields the LLM is asked to fill in (its response schema)."""

    priority: Literal[
        "LOW",
        "MEDIUM",
        "HIGH",
        "CRITICAL",
    ] = Field(
        description="Patient triage priority."
    )

    confidence: float = Field(
        description=(
            "Confidence in the triage recommendation, "
            "between 0.0 and 1.0."
        ),
        ge=0.0,
        le=1.0,
    )

    reasoning: str = Field(
        description=(
            "Concise explanation based only on the "
            "provided patient information."
        )
    )

    recommended_action: str = Field(
        description=(
            "Recommended next clinical workflow action. "
            "Do not prescribe medication."
        )
    )


class TriageResult(TriageModelOutput):
    """Triage output after the confidence score has been calibrated."""

    confidence_factors: list[str] = Field(
        default_factory=list,
        description="Why the confidence score is what it is.",
    )


def confidence_level(confidence: float) -> str:
    if confidence >= HIGH_CONFIDENCE:
        return "HIGH"
    if confidence >= REVIEW_THRESHOLD:
        return "MEDIUM"
    return "LOW"


def triage_to_dict(triage: TriageResult) -> dict:
    """API shape for a triage result, including the confidence score."""
    return {
        "priority": triage.priority,
        "confidence": triage.confidence,
        "confidence_pct": round(triage.confidence * 100),
        "confidence_level": confidence_level(triage.confidence),
        "needs_review": triage.confidence < REVIEW_THRESHOLD,
        "confidence_factors": list(triage.confidence_factors),
        "reasoning": triage.reasoning,
        "recommended_action": triage.recommended_action,
    }
