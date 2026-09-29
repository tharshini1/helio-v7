from app.agents.triage_agent import TriageAgent
from app.agents.monitoring_agent import (
    MonitoringResult,
    MonitoringSeverity,
)


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


agent = TriageAgent()

result = agent._rule_based_triage(
    patient=MockPatient(),
    monitoring_result=monitoring_result,
)

print("\n===== HELIO FALLBACK TRIAGE =====")
print("Priority:", result.priority)
print("Confidence:", result.confidence)
print("Reasoning:", result.reasoning)
print("Recommended Action:", result.recommended_action)
print("====================================")