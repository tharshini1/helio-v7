from datetime import datetime

# Draft medication classes by symptom keyword. This is a DRAFT for the
# responsible doctor to verify/edit before approving - never final advice.
MEDICATION_RULES = [
    ("fever", "Paracetamol 500 mg as needed for fever"),
    ("chill", "Paracetamol 500 mg as needed"),
    ("cough", "Cough syrup (as prescribed)"),
    ("sore throat", "Throat lozenges / warm saline gargles"),
    ("wheez", "Bronchodilator inhaler (as prescribed)"),
    ("breath", "Oxygen support / bronchodilator (as prescribed)"),
    ("chest", "Cardiac medication (as prescribed)"),
    ("palpitation", "Cardiac medication (as prescribed)"),
    ("headache", "Analgesic (as prescribed)"),
    ("body ache", "Analgesic (as prescribed)"),
    ("pain", "Analgesic (as prescribed)"),
    ("dizz", "IV fluids / ORS"),
    ("weakness", "ORS and multivitamin"),
    ("fatigue", "Multivitamin"),
    ("nausea", "Antiemetic (as prescribed)"),
]


class DischargeAgent:
    """Drafts every field of a discharge summary except the amount.

    The amount is entered by billing staff; approval is doctor-only.
    """

    @staticmethod
    def _fmt(dt) -> str:
        return dt.strftime("%Y-%m-%d") if dt else ""

    def draft(self, patient, admitted_at, responsible_doctor, now: datetime) -> dict:
        text = (patient.symptoms or "").lower()
        meds = []
        for keyword, med in MEDICATION_RULES:
            if keyword in text and med not in meds:
                meds.append(med)
        if not meds:
            meds = ["No medication recorded - doctor to confirm"]

        diagnosis = (
            f"Presented with {patient.symptoms}" if patient.symptoms and patient.symptoms != "No symptoms"
            else "General observation / no acute symptoms"
        )
        return {
            "admission_date": self._fmt(admitted_at or now),
            "discharge_date": self._fmt(now),
            "diagnosis": diagnosis,
            "medication": "\n".join(meds),
            "doctor_id": responsible_doctor.id if responsible_doctor else None,
        }
