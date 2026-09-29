try:
    from google import genai
except ImportError:  # pragma: no cover
    genai = None

from app.core.config import settings
from app.schemas.triage import TriageModelOutput, TriageResult


class TriageAgent:
    """
    Helio Triage Agent.

    Primary path:
        Gemini-powered triage reasoning.

    Fallback path:
        Deterministic rule-based triage when Gemini is
        unavailable, rate-limited, or times out.
    """

    def __init__(self):
        # Gemini is optional: without a key (or the library) the agent
        # transparently uses the deterministic rule-based triage.
        self.client = None

        if settings.GEMINI_API_KEY and genai is not None:
            try:
                self.client = genai.Client(
                    api_key=settings.GEMINI_API_KEY
                )
            except Exception as error:
                print(f"[Triage Agent] Gemini disabled: {error}")

        self.model = settings.GEMINI_MODEL

    def assess_patient(self, patient, monitoring_result) -> TriageResult:
        """
        Try Gemini first.

        If Gemini fails for any reason, use deterministic
        rule-based triage so the hospital workflow can continue.
        Either way the confidence score is calibrated afterwards.
        """

        if self.client is None:
            result = self._rule_based_triage(patient, monitoring_result)
            return self._calibrate(result, patient, monitoring_result)

        try:
            result = self._gemini_triage(patient, monitoring_result)

        except Exception as error:
            print(
                f"[Triage Agent] Gemini unavailable: {error}"
            )

            result = self._rule_based_triage(patient, monitoring_result)

        return self._calibrate(result, patient, monitoring_result)

    def assess_without_escalation(self, patient, monitoring_result) -> TriageResult:
        """Vitals are normal, so no LLM call is needed: routine LOW priority."""
        result = TriageResult(
            priority="LOW",
            confidence=0.90,
            reasoning=(
                "Monitoring found no vital-sign abnormalities, so no "
                "triage escalation is required."
            ),
            recommended_action=(
                "Continue routine monitoring and standard hospital workflow."
            ),
        )
        return self._calibrate(result, patient, monitoring_result)

    # ------------------------------------------------------------------
    # Confidence calibration
    # ------------------------------------------------------------------

    # Priorities that are consistent with each monitoring severity.
    _EXPECTED_PRIORITIES = {
        "CRITICAL": {"CRITICAL"},
        "WARNING": {"MEDIUM", "HIGH", "CRITICAL"},
        "NORMAL": {"LOW", "MEDIUM"},
    }

    def _calibrate(self, result: TriageResult, patient, monitoring_result) -> TriageResult:
        """
        Turn the raw confidence into a score we can defend.

        An LLM's self-reported confidence is not reliable on its own, so it is
        reduced when the input data is incomplete and capped when the priority
        contradicts the deterministic Monitoring Agent.
        """
        confidence = float(result.confidence)
        factors: list[str] = []

        missing = [
            label
            for label, value in (
                ("heart rate", getattr(patient, "heart_rate", None)),
                ("SpO2", getattr(patient, "spo2", None)),
                ("temperature", getattr(patient, "temperature", None)),
            )
            if value is None
        ]
        if missing:
            confidence -= 0.12 * len(missing)
            factors.append(f"Missing vitals: {', '.join(missing)}")

        symptoms = (getattr(patient, "symptoms", None) or "").strip()
        if not symptoms or symptoms.lower() == "no symptoms":
            confidence -= 0.05
            factors.append("No symptoms recorded")

        if not getattr(patient, "age", None):
            confidence -= 0.05
            factors.append("Age not recorded")

        severity = monitoring_result.severity.value
        if result.priority not in self._EXPECTED_PRIORITIES.get(severity, set()):
            confidence = min(confidence, 0.55)
            factors.append(
                f"Priority {result.priority} differs from monitoring severity {severity}"
            )

        if not factors:
            factors.append("All vitals recorded and consistent with monitoring severity")

        confidence = round(min(max(confidence, 0.05), 0.99), 2)
        return TriageResult(
            priority=result.priority,
            confidence=confidence,
            reasoning=result.reasoning,
            recommended_action=result.recommended_action,
            confidence_factors=factors,
        )

    def _gemini_triage(
        self,
        patient,
        monitoring_result
    ) -> TriageResult:

        prompt = f"""
You are the Triage Agent in Helio, an autonomous hospital
operations coordination system.

Assess patient urgency using ONLY the information provided.

PATIENT
-------
Patient code: {patient.patient_code}
Name: {patient.name}
Age: {patient.age}
Gender: {patient.gender}
Symptoms: {patient.symptoms}
Heart rate: {patient.heart_rate}
SpO2: {patient.spo2}
Temperature: {patient.temperature}
Status: {patient.status}

MONITORING AGENT
----------------
Severity: {monitoring_result.severity.value}
Abnormal signals: {monitoring_result.abnormal_signals}
Summary: {monitoring_result.summary}

Priority must be exactly:
LOW, MEDIUM, HIGH, or CRITICAL.

Return:
- priority
- confidence between 0.0 and 1.0
- concise reasoning
- recommended next hospital workflow action

Do not prescribe medication.
Do not invent patient information.
Do not modify hospital resources.
"""

        response_format = {
            "type": "text",
            "mime_type": "application/json",
            "schema": TriageModelOutput.model_json_schema(),
        }

        interaction = self.client.interactions.create(
            model=self.model,
            input=prompt,
            response_format=response_format,
        )

        if not interaction.output_text:
            raise RuntimeError(
                "Gemini returned an empty response."
            )

        output = TriageModelOutput.model_validate_json(
            interaction.output_text
        )

        return TriageResult(**output.model_dump())

    def _rule_based_triage(
        self,
        patient,
        monitoring_result
    ) -> TriageResult:

        severity = monitoring_result.severity.value

        # CRITICAL conditions
        if severity == "CRITICAL":
            return TriageResult(
                priority="CRITICAL",
                confidence=0.95,
                reasoning=(
                    "Rule-based fallback activated because the "
                    "Gemini service was unavailable. The Monitoring "
                    "Agent identified critical vital-sign abnormalities."
                ),
                recommended_action=(
                    "Escalate immediately to the critical-care "
                    "workflow and notify the responsible clinical team."
                ),
            )

        # WARNING conditions
        if severity == "WARNING":
            return TriageResult(
                priority="HIGH",
                confidence=0.90,
                reasoning=(
                    "Rule-based fallback activated because the "
                    "Gemini service was unavailable. The Monitoring "
                    "Agent identified abnormal vital signs requiring "
                    "prompt clinical review."
                ),
                recommended_action=(
                    "Prioritize clinical assessment and notify "
                    "the responsible clinical team."
                ),
            )

        # NORMAL conditions
        return TriageResult(
            priority="LOW",
            confidence=0.85,
            reasoning=(
                "Rule-based fallback activated because the "
                "Gemini service was unavailable. No critical "
                "monitoring abnormalities were detected."
            ),
            recommended_action=(
                "Continue routine monitoring and standard "
                "hospital workflow."
            ),
        )