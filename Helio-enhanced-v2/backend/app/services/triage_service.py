from app.agents.monitoring_agent import MonitoringAgent
from app.agents.triage_agent import TriageAgent
from app.governance.risk_engine import RiskEngine
from app.schemas.triage import triage_to_dict


class TriageService:

    def __init__(self):
        self.monitoring_agent = MonitoringAgent()
        self.triage_agent = TriageAgent()
        self.risk_engine = RiskEngine()

    def process_patient(self, patient):

        # 1. Monitoring Agent evaluates the patient
        monitoring_result = (
            self.monitoring_agent.evaluate_patient(patient)
        )

        # 2. Triage is not required
        if not monitoring_result.requires_triage:
            return {
                "status": "NOT_REQUIRED",
                "monitoring": {
                    "severity": monitoring_result.severity.value,
                    "abnormal_signals": (
                        monitoring_result.abnormal_signals
                    ),
                    "summary": monitoring_result.summary,
                },
            }

        # 3. Triage Agent evaluates urgency
        triage_result = self.triage_agent.assess_patient(
            patient=patient,
            monitoring_result=monitoring_result,
        )

        # 4. Determine the operational action
        action = self._determine_action(
            triage_result.priority
        )

        # 5. Risk Engine classifies the action
        risk_decision = self.risk_engine.classify(action)

        return {
            "status": "COMPLETED",

            "monitoring": {
                "severity": monitoring_result.severity.value,
                "abnormal_signals": (
                    monitoring_result.abnormal_signals
                ),
                "summary": monitoring_result.summary,
            },

            "triage": triage_to_dict(triage_result),

            "governance": risk_decision.to_dict(),
        }

    def _determine_action(self, priority: str) -> str:

        if priority == "CRITICAL":
            return "EMERGENCY_REPRIORITIZATION"

        if priority == "HIGH":
            return "EMERGENCY_REPRIORITIZATION"

        if priority == "MEDIUM":
            return "QUEUE_REORDER"

        return "STATUS_REFRESH"