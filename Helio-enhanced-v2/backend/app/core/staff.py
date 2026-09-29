"""Authorised Helio login accounts.

Only these accounts can sign in. The doctors and nurses shown in the app come
from app/database/data/doctors_and_nurses.csv (see seed.py).
"""
import hmac

STAFF_PASSWORD = "123"

STAFF = [
    {
        "email": "tharshini@gmail.com",
        "name": "Dr. Tharshini",
        "role": "Doctor",
        "department": "Emergency",
        "specialization": "Emergency Medicine",
    },
    {
        "email": "eva@gmail.com",
        "name": "Dr. Eva",
        "role": "Doctor",
        "department": "Cardiology",
        "specialization": "Cardiology",
    },
    {
        "email": "tahseen@gmail.com",
        "name": "Nurse Tahseen",
        "role": "Nurse",
        "department": "Emergency",
    },
    {
        "email": "hawwa@gmail.com",
        "name": "Nurse Hawwa",
        "role": "Nurse",
        "department": "Cardiology",
    },
]


def authenticate(email: str, password: str):
    """Return the staff record for valid credentials, otherwise None."""
    email = (email or "").strip().lower()
    for member in STAFF:
        if member["email"] == email:
            if hmac.compare_digest(password or "", STAFF_PASSWORD):
                return member
            return None
    return None
