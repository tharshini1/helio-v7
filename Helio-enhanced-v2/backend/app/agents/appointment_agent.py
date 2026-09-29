from dataclasses import dataclass, field

# keyword -> {specialization: weight}. Rule-based (no paid API needed).
# Nothing maps a symptom to a named doctor: symptoms -> specialization ->
# doctors that actually exist in the database and are currently available.
SYMPTOM_RULES: list[tuple[str, dict[str, int]]] = [
    ("shortness of breath", {"Cardiology": 3, "Pulmonology": 2}),
    ("chest", {"Cardiology": 4}),
    ("palpitation", {"Cardiology": 4}),
    ("faint", {"Cardiology": 3}),
    ("lightheaded", {"Cardiology": 2}),
    ("sweating", {"Cardiology": 1}),
    ("heart", {"Cardiology": 3}),
    ("wheez", {"Pulmonology": 4}),
    ("cough", {"Pulmonology": 3}),
    ("rapid breathing", {"Pulmonology": 3}),
    ("bluish", {"Pulmonology": 3, "Emergency & Urgent Care": 1}),
    ("breath", {"Pulmonology": 1}),
    ("fever", {"Infectious Diseases": 3}),
    ("chills", {"Infectious Diseases": 2}),
    ("sore throat", {"Infectious Diseases": 2}),
    ("runny nose", {"Infectious Diseases": 2}),
    ("infection", {"Infectious Diseases": 3}),
    ("kidney", {"Nephrology and Urology Science": 4}),
    ("urine", {"Nephrology and Urology Science": 3}),
    ("swelling", {"Nephrology and Urology Science": 1, "General Medicine": 1}),
    ("confusion", {"Emergency & Urgent Care": 2, "Neurology & Neurosurgery": 2, "General Medicine": 1}),
    ("delirium", {"Emergency & Urgent Care": 3}),
    ("seizure", {"Emergency & Urgent Care": 4, "Neurology & Neurosurgery": 2}),
    ("unconscious", {"Emergency & Urgent Care": 5}),
    ("bleeding", {"Emergency & Urgent Care": 4}),
    ("trauma", {"Emergency & Urgent Care": 4, "Orthopaedics": 2}),
    ("severe", {"Emergency & Urgent Care": 1}),
    ("dizz", {"General Medicine": 2, "Neurology & Neurosurgery": 1}),
    ("headache", {"Neurology & Neurosurgery": 2, "General Medicine": 1}),
    ("fatigue", {"General Medicine": 2}),
    ("weakness", {"General Medicine": 2, "Neurology & Neurosurgery": 1}),
    ("body ache", {"General Medicine": 2}),
]

FALLBACK_SPECIALIZATIONS = ["General Medicine", "Emergency & Urgent Care"]


@dataclass
class AppointmentRecommendation:
    patient_id: int
    patient_code: str
    specialization: str | None
    candidate_specializations: list[str]
    recommended_doctor: dict | None
    alternatives: list[dict] = field(default_factory=list)
    available: bool = False
    reason: str = ""

    def to_dict(self) -> dict:
        return self.__dict__.copy()


class AppointmentAgent:
    """Analyses a patient's record and recommends an available doctor."""

    def determine_specializations(self, patient) -> tuple[list[str], list[str]]:
        text = (patient.symptoms or "").lower()
        scores: dict[str, int] = {}
        matched: list[str] = []

        for keyword, weights in SYMPTOM_RULES:
            if keyword in text:
                matched.append(keyword)
                for spec, weight in weights.items():
                    scores[spec] = scores.get(spec, 0) + weight

        # Vitals (only when they exist in the record)
        if patient.spo2 and patient.spo2 < 92:
            scores["Pulmonology"] = scores.get("Pulmonology", 0) + 2
            matched.append(f"SpO2 {patient.spo2}%")
        if patient.heart_rate and patient.heart_rate > 120:
            scores["Cardiology"] = scores.get("Cardiology", 0) + 2
            matched.append(f"heart rate {patient.heart_rate}")
        if patient.temperature and patient.temperature >= 38:
            scores["Infectious Diseases"] = scores.get("Infectious Diseases", 0) + 1
            matched.append(f"temperature {patient.temperature}")
        if patient.age is not None and patient.age <= 14:
            scores["Paediatrics and Neonatology"] = scores.get("Paediatrics and Neonatology", 0) + 5
            matched.append(f"age {patient.age}")

        ranked = [s for s, _ in sorted(scores.items(), key=lambda kv: -kv[1])]
        for spec in FALLBACK_SPECIALIZATIONS:
            if spec not in ranked:
                ranked.append(spec)
        return ranked, matched

    @staticmethod
    def _doctor_dict(doctor) -> dict:
        return {
            "id": doctor.id,
            "name": doctor.name,
            "specialization": doctor.specialization,
            "years_experience": doctor.years_experience,
            "is_available": doctor.is_available,
        }

    def recommend(self, patient, doctors) -> AppointmentRecommendation:
        ranked, matched = self.determine_specializations(patient)
        basis = ", ".join(matched) if matched else "no specific symptoms recorded"

        for index, spec in enumerate(ranked):
            available = sorted(
                (
                    d for d in doctors
                    if d.specialization.lower() == spec.lower() and d.is_available
                ),
                key=lambda d: -(d.years_experience or 0),
            )
            if not available:
                continue

            primary = ranked[0]
            note = (
                ""
                if index == 0
                else f" No {primary} doctor is currently available, so the "
                     f"next suitable specialization was used."
            )
            return AppointmentRecommendation(
                patient_id=patient.id,
                patient_code=patient.patient_code,
                specialization=spec,
                candidate_specializations=ranked,
                recommended_doctor=self._doctor_dict(available[0]),
                alternatives=[self._doctor_dict(d) for d in available[1:4]],
                available=True,
                reason=(
                    f"Based on {basis}, {spec} is the most suitable "
                    f"specialization. {available[0].name} is currently "
                    f"available.{note}"
                ),
            )

        return AppointmentRecommendation(
            patient_id=patient.id,
            patient_code=patient.patient_code,
            specialization=ranked[0] if ranked else None,
            candidate_specializations=ranked,
            recommended_doctor=None,
            available=False,
            reason=(
                f"Based on {basis}, {ranked[0]} is suitable, but no suitable "
                f"doctor is currently available."
            ),
        )
