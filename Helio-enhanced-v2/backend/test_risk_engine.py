from app.governance.risk_engine import RiskEngine


engine = RiskEngine()


actions = [
    "BED_REASSIGNMENT",
    "EMERGENCY_REPRIORITIZATION",
    "DISCHARGE_APPROVAL",
    "NOTIFICATION",
    "QUEUE_REORDER",
    "ROUTINE_DIAGNOSTIC_SLOT",
]


print("\n===== HELIO RISK ENGINE =====")

for action in actions:
    decision = engine.classify(action)

    print(
        f"{decision.action} -> "
        f"Risk: {decision.risk_level.value} | "
        f"Approval: {decision.approval_status.value}"
    )

print("================================")