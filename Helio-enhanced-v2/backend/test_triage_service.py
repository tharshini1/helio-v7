from app.agents.monitoring_agent import (
    MonitoringResult,
    MonitoringSeverity,
)
from app.agents.triage_agent import TriageAgent
from app.services.triage_service import TriageService
from app.schemas.triage import TriageResult


class MockPatient:
    id = 3
    patient_code = "P003"
    name = "Rahul"
    age = 61
    gender = "M"
    symptoms = "Shortness of breath"
    heart_rate = 132
    spo2 = 88
    temperature = 38.9
    status = "CRITICAL"


patient = MockPatient()


monitoring_result = MonitoringResult(
    patient_id=3,
    patient_code="P003",
    severity=MonitoringSeverity.CRITICAL,
    abnormal_signals=[
        "High heart rate: 132 bpm",
        "Low SpO2: 88%",
    ],
    summary="Critical vital-sign abnormalities detected.",
    requires_triage=True,
)


# Create the service
service = TriageService()


# Temporarily replace Gemini triage with our
# deterministic fallback for this test.
def fake_assess_patient(patient, monitoring_result):

    return TriageResult(
        priority="CRITICAL",
        confidence=0.95,
        reasoning="Fallback triage result for testing.",
        recommended_action=(
            "Escalate to critical-care workflow."
        ),
    )


service.triage_agent.assess_patient = fake_assess_patient


result = service.process_patient(patient)


print("\n===== HELIO TRIAGE SERVICE =====")
print("Status:", result["status"])

print("\nMonitoring:")
print(result["monitoring"])

print("\nTriage:")
print(result["triage"])

print("\nGovernance:")
print(result["governance"])

print("===================================")