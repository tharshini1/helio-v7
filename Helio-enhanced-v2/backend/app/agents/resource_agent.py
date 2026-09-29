from dataclasses import dataclass


@dataclass
class BedAllocationResult:
    patient_id: int
    patient_code: str
    priority: str

    category: str
    recommended_ward: str          # required ward (ICU / GENERAL MEDICINE / ER)
    recommended_bed: str | None

    available: bool
    requires_approval: bool

    reason: str

    @property
    def required_ward(self) -> str:
        return self.recommended_ward


# Ward names as stored in the beds table may vary; match on aliases only.
WARD_ALIASES = {
    "ICU": {"ICU"},
    "GENERAL MEDICINE": {"GENERAL MEDICINE", "GM", "GENERAL"},
    "ER": {"ER", "EMERGENCY", "EMERGENCY ROOM"},
}


class ResourceAgent:
    """
    Helio Bed / Resource Agent.

    Strict mapping (never substitutes another ward):
        NEW PATIENT -> ER
        CRITICAL    -> ICU
        NORMAL      -> GENERAL MEDICINE

    Reads actual bed records, never mutates them, and always requires
    human approval before allocation.
    """

    @staticmethod
    def categorize(patient, priority: str) -> tuple[str, str]:
        if (getattr(patient, "status", "") or "").upper() == "NEW":
            return "NEW PATIENT", "ER"
        if priority == "CRITICAL":
            return "CRITICAL", "ICU"
        return "NORMAL", "GENERAL MEDICINE"

    def allocate_bed(self, patient, priority: str, beds) -> BedAllocationResult:
        priority = (priority or "LOW").upper()
        category, ward = self.categorize(patient, priority)
        aliases = WARD_ALIASES[ward]

        ward_beds = sorted(
            (b for b in beds if (b.ward_type or "").strip().upper() in aliases),
            key=lambda b: b.bed_code,
        )
        free = [b for b in ward_beds if not b.is_occupied]

        base = dict(
            patient_id=patient.id,
            patient_code=patient.patient_code,
            priority=priority,
            category=category,
            recommended_ward=ward,
            requires_approval=True,
        )

        if not free:
            return BedAllocationResult(
                **base,
                recommended_bed=None,
                available=False,
                reason=(
                    f"Patient is {category} and requires {ward}, but no {ward} "
                    f"bed is available. The patient was NOT moved to another "
                    f"ward. Human intervention is required."
                ),
            )

        bed = free[0]
        return BedAllocationResult(
            **base,
            recommended_bed=bed.bed_code,
            available=True,
            reason=(
                f"Patient is {category} and requires {ward}; "
                f"{bed.bed_code} is available. Awaiting human approval."
            ),
        )
