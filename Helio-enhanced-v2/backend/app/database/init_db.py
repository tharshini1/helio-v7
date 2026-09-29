from sqlalchemy import inspect, text

from app.database.base import Base
from app.database.connection import engine

# Import all models so SQLAlchemy knows about them.
from app.models import (
    Department,
    Doctor,
    Patient,
    Bed,
    Nurse,
    AuditLog,
    DischargeRequest,
    DiagnosticRequest,
    EmergencyAlert,
)

# Columns added after the first release (existing databases get them on startup).
NEW_COLUMNS = {
    "discharge_requests": {
        "admission_date": "VARCHAR(30)",
        "discharge_date": "VARCHAR(30)",
        "diagnosis": "VARCHAR(500)",
        "medication": "VARCHAR(1000)",
        "amount": "FLOAT",
        "approved_by": "VARCHAR(100)",
    },
    "patients": {
        "email": "VARCHAR(120)",
        "phone": "VARCHAR(20)",
        "password_hash": "VARCHAR(200)",
    },
    "diagnostic_requests": {
        "image_filename": "VARCHAR(200)",
        "image_mime": "VARCHAR(50)",
        "image_data": "BLOB",  # swapped for BYTEA on PostgreSQL below
        "image_uploaded_by": "VARCHAR(100)",
        "image_uploaded_at": "DATETIME",
        "ai_available": "BOOLEAN",
        "ai_problem": "VARCHAR(300)",
        "ai_reason": "TEXT",
        "ai_confidence": "FLOAT",
        "ai_urgency": "VARCHAR(20)",
        "ai_report": "TEXT",
        "ai_model": "VARCHAR(80)",
        "ai_analysed_at": "DATETIME",
        "reviewed_by": "VARCHAR(100)",
    },
    "appointments": {
        "visited_at": "DATETIME",
        "visited_by": "VARCHAR(100)",
        "bed_needed": "BOOLEAN",
        "bed_decision_by": "VARCHAR(100)",
        "bed_decision_at": "DATETIME",
        "bed_code": "VARCHAR(20)",
    },
}

# One live appointment per doctor per slot, enforced by the database so two
# simultaneous bookings can never both succeed.
ACTIVE_SLOT_INDEX = (
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_active_doctor_slot "
    "ON appointments (doctor_id, appointment_date, appointment_time) "
    "WHERE status IN ('SCHEDULED', 'VISITED', 'COMPLETED')"
)


def init_database():
    Base.metadata.create_all(bind=engine)

    inspector = inspect(engine)
    with engine.begin() as connection:
        for table, columns in NEW_COLUMNS.items():
            if table not in inspector.get_table_names():
                continue
            existing = {c["name"] for c in inspector.get_columns(table)}
            for name, ddl in columns.items():
                if name not in existing:
                    if engine.dialect.name == "postgresql":
                        ddl = ddl.replace("BLOB", "BYTEA").replace("DATETIME", "TIMESTAMP")
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))

    try:
        with engine.begin() as connection:
            connection.execute(text(ACTIVE_SLOT_INDEX))
    except Exception as error:  # e.g. old data already has a double booking
        print(f"[init_db] Could not create the doctor-slot unique index: {error}")
