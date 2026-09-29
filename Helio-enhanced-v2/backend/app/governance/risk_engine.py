from enum import Enum


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ApprovalStatus(str, Enum):
    AUTO = "AUTO"
    REQUIRED = "REQUIRED"


class RiskDecision:
    def __init__(
        self,
        action: str,
        risk_level: RiskLevel,
        approval_status: ApprovalStatus,
        reason: str,
    ):
        self.action = action
        self.risk_level = risk_level
        self.approval_status = approval_status
        self.reason = reason

    def to_dict(self):
        return {
            "action": self.action,
            "risk_level": self.risk_level.value,
            "approval_status": self.approval_status.value,
            "reason": self.reason,
        }


class RiskEngine:

    GATED_ACTIONS = {
        "BED_REASSIGNMENT",
        "ALTERNATE_WARD_ADMISSION",
        "EMERGENCY_REPRIORITIZATION",
        "DISCHARGE_APPROVAL",
        "MAJOR_SCHEDULE_DISRUPTION",
        "CRITICAL_PRIORITIZATION_CHANGE",
    }

    AUTO_ACTIONS = {
        "ROUTINE_BOOKING",
        "NOTIFICATION",
        "ROUTINE_DIAGNOSTIC_SLOT",
        "QUEUE_REORDER",
        "STATUS_REFRESH",
    }

    def classify(self, action: str) -> RiskDecision:

        action = action.upper()

        if action in self.GATED_ACTIONS:
            return RiskDecision(
                action=action,
                risk_level=RiskLevel.HIGH,
                approval_status=ApprovalStatus.REQUIRED,
                reason=(
                    "This action can affect another patient's "
                    "allocation or care path and therefore requires "
                    "human approval."
                ),
            )

        if action in self.AUTO_ACTIONS:
            return RiskDecision(
                action=action,
                risk_level=RiskLevel.LOW,
                approval_status=ApprovalStatus.AUTO,
                reason=(
                    "This action is informational or routine and "
                    "does not directly alter another patient's care path."
                ),
            )

        # Unknown actions are safer when gated.
        return RiskDecision(
            action=action,
            risk_level=RiskLevel.HIGH,
            approval_status=ApprovalStatus.REQUIRED,
            reason=(
                "Unknown action type. Human approval is required "
                "before execution."
            ),
        )