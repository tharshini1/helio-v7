"""Emergency paging: pick the right doctors for a critical arrival.

Rule-based on purpose (no external API): each emergency type maps to an ordered
list of specialties. The first specialty that has an available doctor wins, and
up to MAX_PAGED of its most experienced available doctors are paged.
"""
import json
from datetime import datetime

MAX_PAGED = 3

# Specialty names match the hospital specialty list used in the doctor roster.
EMERGENCY_TYPES: dict[str, dict] = {
    "road_accident": {
        "label": "Road accident / major trauma",
        "specialties": ["Emergency & Urgent Care", "Orthopaedics", "Critical Care"],
    },
    "cardiac_arrest": {
        "label": "Cardiac arrest / heart attack",
        "specialties": ["Cardiology", "Emergency & Urgent Care", "Critical Care"],
    },
    "stroke": {
        "label": "Stroke / head injury",
        "specialties": ["Neurology & Neurosurgery", "Emergency & Urgent Care", "Critical Care"],
    },
    "respiratory": {
        "label": "Severe breathing difficulty",
        "specialties": ["Pulmonology", "Critical Care", "Emergency & Urgent Care"],
    },
    "severe_bleeding": {
        "label": "Severe bleeding",
        "specialties": ["Emergency & Urgent Care", "General Surgery", "Vascular Surgery"],
    },
    "burns": {
        "label": "Major burns",
        "specialties": ["Plastic Surgery", "Emergency & Urgent Care", "Critical Care"],
    },
    "fracture": {
        "label": "Multiple fractures / spine injury",
        "specialties": ["Orthopaedics", "Emergency & Urgent Care", "Anesthesiology"],
    },
    "other_critical": {
        "label": "Other critical condition",
        "specialties": ["Emergency & Urgent Care", "Critical Care", "General Medicine"],
    },
}


def list_types() -> list[dict]:
    return [
        {"key": key, "label": value["label"], "specialty": value["specialties"][0]}
        for key, value in EMERGENCY_TYPES.items()
    ]


def route(emergency_type: str, doctors) -> tuple[str | None, list]:
    """Return (specialty, doctors to page) for an emergency type."""
    config = EMERGENCY_TYPES.get(emergency_type)
    if config is None:
        return None, []

    for specialty in config["specialties"]:
        available = sorted(
            (
                d for d in doctors
                if d.specialization.lower() == specialty.lower() and d.is_available
            ),
            key=lambda d: (-(d.years_experience or 0), d.id),
        )
        if available:
            return specialty, available[:MAX_PAGED]

    return config["specialties"][0], []


def doctor_summary(doctor) -> dict:
    return {
        "id": doctor.id,
        "name": doctor.name,
        "specialization": doctor.specialization,
        "years_experience": doctor.years_experience,
    }


def alert_dict(alert) -> dict:
    try:
        paged = json.loads(alert.paged_doctors or "[]")
    except ValueError:
        paged = []

    return {
        "id": alert.id,
        "emergency_type": alert.emergency_type,
        "emergency_label": alert.emergency_label,
        "required_specialty": alert.required_specialty,
        "patient_label": alert.patient_label,
        "location": alert.location,
        "notes": alert.notes,
        "paged_doctors": paged,
        "status": alert.status,
        "raised_by": alert.raised_by,
        "created_at": alert.created_at.isoformat() + "Z" if alert.created_at else None,
        "acknowledged_by": alert.acknowledged_by,
        "acknowledged_at": (
            alert.acknowledged_at.isoformat() + "Z" if alert.acknowledged_at else None
        ),
    }


def now() -> datetime:
    return datetime.utcnow()
