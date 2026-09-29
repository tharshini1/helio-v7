from dataclasses import dataclass
from enum import Enum


class MonitoringSeverity(str, Enum):
    NORMAL = "NORMAL"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass
class MonitoringResult:
    patient_id: int
    patient_code: str
    severity: MonitoringSeverity
    abnormal_signals: list[str]
    summary: str
    requires_triage: bool


class MonitoringAgent:
    """
    Helio Monitoring / Patient Flow Agent.

    Responsibilities:
    - Observe patient vitals.
    - Detect abnormal signals.
    - Assign an objective monitoring severity.
    - Trigger the Triage Agent when necessary.

    This agent does NOT use an LLM.
    """

    def evaluate_patient(self, patient) -> MonitoringResult:

        abnormal_signals = []

        heart_rate = patient.heart_rate
        spo2 = patient.spo2
        temperature = patient.temperature

        # ---------------------------------------------------------
        # HEART RATE
        # ---------------------------------------------------------

        if heart_rate is not None:

            if heart_rate < 50:
                abnormal_signals.append(
                    f"Low heart rate: {heart_rate} bpm"
                )

            elif heart_rate > 120:
                abnormal_signals.append(
                    f"High heart rate: {heart_rate} bpm"
                )

            elif heart_rate > 100:
                abnormal_signals.append(
                    f"Elevated heart rate: {heart_rate} bpm"
                )

        # ---------------------------------------------------------
        # SPO2
        # ---------------------------------------------------------

        if spo2 is not None:

            if spo2 < 90:
                abnormal_signals.append(
                    f"Critically low SpO2: {spo2}%"
                )

            elif spo2 < 94:
                abnormal_signals.append(
                    f"Low SpO2: {spo2}%"
                )

        # ---------------------------------------------------------
        # TEMPERATURE
        # ---------------------------------------------------------

        if temperature is not None:

            if temperature >= 39:
                abnormal_signals.append(
                    f"High temperature: {temperature}°C"
                )

            elif temperature >= 38:
                abnormal_signals.append(
                    f"Elevated temperature: {temperature}°C"
                )

        # ---------------------------------------------------------
        # DETERMINE SEVERITY
        # ---------------------------------------------------------

        severity = self._determine_severity(
            heart_rate=heart_rate,
            spo2=spo2,
            temperature=temperature,
        )

        # ---------------------------------------------------------
        # GENERATE SUMMARY
        # ---------------------------------------------------------

        if severity == MonitoringSeverity.NORMAL:

            summary = "No significant vital-sign abnormalities detected."

        elif severity == MonitoringSeverity.WARNING:

            summary = (
                "One or more abnormal vital signs detected. "
                "Patient should be monitored and evaluated."
            )

        else:

            summary = (
                "Critical vital-sign abnormality detected. "
                "Immediate triage evaluation is required."
            )

        return MonitoringResult(
            patient_id=patient.id,
            patient_code=patient.patient_code,
            severity=severity,
            abnormal_signals=abnormal_signals,
            summary=summary,
            requires_triage=severity != MonitoringSeverity.NORMAL,
        )

    # -------------------------------------------------------------
    # SEVERITY LOGIC
    # -------------------------------------------------------------

    def _determine_severity(
    self,
    heart_rate: int | None,
    spo2: int | None,
    temperature: float | None,
) -> MonitoringSeverity:

        critical_conditions = 0
        warning_conditions = 0

    # ---------------------------------------------------------
    # HEART RATE
    # ---------------------------------------------------------

        if heart_rate is not None:

            # Critical
            if heart_rate < 40 or heart_rate > 130:
                critical_conditions += 1

        # Warning
            elif heart_rate < 50 or heart_rate > 100:
                warning_conditions += 1

    # ---------------------------------------------------------
    # SPO2
    # ---------------------------------------------------------

        if spo2 is not None:

        # Critical
            if spo2 < 90:
                critical_conditions += 1

        # Warning
            elif spo2 < 94:
                warning_conditions += 1

    # ---------------------------------------------------------
    # TEMPERATURE
    # ---------------------------------------------------------

        if temperature is not None:

        # Critical
            if temperature >= 40:
                critical_conditions += 1

        # Warning
            elif temperature >= 38:
                warning_conditions += 1

    # ---------------------------------------------------------
    # FINAL CLASSIFICATION
    # ---------------------------------------------------------

        if critical_conditions >= 1:
            return MonitoringSeverity.CRITICAL

        if warning_conditions >= 1:
            return MonitoringSeverity.WARNING

        return MonitoringSeverity.NORMAL