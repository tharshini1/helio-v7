from app.agents.monitoring_agent import MonitoringAgent
from app.agents.triage_agent import TriageAgent
from app.schemas.triage import triage_to_dict
from app.agents.resource_agent import ResourceAgent
from app.governance.risk_engine import RiskEngine


class HelioOrchestrator:

    def __init__(self):
        self.monitoring_agent = MonitoringAgent()
        self.triage_agent = TriageAgent()
        self.resource_agent = ResourceAgent()
        self.risk_engine = RiskEngine()

    def process_patient(self, patient, beds):

        handoff = []

        # =========================================
        # 1. MONITORING AGENT
        # =========================================

        monitoring = self.monitoring_agent.evaluate_patient(
            patient
        )

        handoff.append({
            "step": 1,
            "agent": "Monitoring Agent",
            "status": "COMPLETED",
            "message": monitoring.summary,
            "data": {
                "severity": monitoring.severity.value,
                "abnormal_signals": monitoring.abnormal_signals,
            },
        })

        # =========================================
        # 2. TRIAGE AGENT
        # =========================================

        triage = self.triage_agent.assess_patient(
            patient=patient,
            monitoring_result=monitoring,
        )

        handoff.append({
            "step": 2,
            "agent": "Triage Agent",
            "status": "COMPLETED",
            "message": (
                f"Priority {triage.priority} "
                f"with confidence "
                f"{triage.confidence:.0%}"
            ),
            "data": triage_to_dict(triage),
        })

        # =========================================
        # 3. ORCHESTRATOR / RISK GATE
        # =========================================

        if triage.priority in ["CRITICAL", "HIGH"]:
            action = "EMERGENCY_REPRIORITIZATION"

        elif triage.priority == "MEDIUM":
            action = "QUEUE_REORDER"

        else:
            action = "STATUS_REFRESH"

        risk = self.risk_engine.classify(action)

        handoff.append({
            "step": 3,
            "agent": "Orchestrator",
            "status": risk.approval_status.value,
            "message": risk.reason,
            "data": risk.to_dict(),
        })

        # =========================================
        # 4. RESOURCE AGENT
        # =========================================

        resource = self.resource_agent.allocate_bed(
            patient=patient,
            priority=triage.priority,
            beds=beds,
        )

        handoff.append({
            "step": 4,
            "agent": "Resource Agent",
            "status": (
                "COMPLETED"
                if resource.available
                else "NO_RESOURCE"
            ),
            "message": resource.reason,
            "data": {
                "ward": resource.recommended_ward,
                "bed": resource.recommended_bed,
                "available": resource.available,
                "requires_approval": resource.requires_approval,
            },
        })

        # =========================================
        # 5. FINAL DECISION
        # =========================================

        requires_approval = (
            risk.approval_status.value == "REQUIRED"
            or resource.requires_approval
        )

        return {
            "patient_id": patient.id,
            "patient_code": patient.patient_code,

            "monitoring": monitoring,
            "triage": triage,
            "risk": risk,
            "resource": resource,

            "requires_approval": requires_approval,

            "handoff": handoff,
        }