from types import SimpleNamespace

from app.agents.resource_agent import ResourceAgent


patient = SimpleNamespace(
    id=3,
    patient_code="P003",
)

beds = [
    SimpleNamespace(
        id=1,
        bed_code="ICU-01",
        ward_type="ICU",
        is_occupied=True,
    ),
    SimpleNamespace(
        id=2,
        bed_code="ICU-02",
        ward_type="ICU",
        is_occupied=False,
    ),
    SimpleNamespace(
        id=3,
        bed_code="ER-01",
        ward_type="ER",
        is_occupied=False,
    ),
]


agent = ResourceAgent()

result = agent.allocate_bed(
    patient=patient,
    priority="CRITICAL",
    beds=beds,
)

print("\n===== HELIO RESOURCE AGENT =====")
print("Patient:", result.patient_code)
print("Priority:", result.priority)
print("Recommended Ward:", result.recommended_ward)
print("Recommended Bed:", result.recommended_bed)
print("Available:", result.available)
print("Requires Approval:", result.requires_approval)
print("Reason:", result.reason)
print("===================================\n")