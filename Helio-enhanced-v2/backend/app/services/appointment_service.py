import os
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.core.clock import now
from app.models import Doctor, Patient
from app.models.appointment import Appointment
from app.services.audit_service import AuditService

SCHEDULED = "SCHEDULED"
CANCELLED = "CANCELLED"
AUTO_CANCELLED = "AUTO_CANCELLED"  # legacy status, kept so old rows still display
COMPLETED = "COMPLETED"
VISITED = "VISITED"
NOT_VISITED = "NOT_VISITED"

# A doctor's slot is taken while an appointment in one of these states holds it.
SLOT_HOLDING = (SCHEDULED, VISITED, COMPLETED)

# Bookable slot grid shown in the UI (the time field still accepts any time).
SLOT_START_HOUR = 9
SLOT_END_HOUR = 17
SLOT_MINUTES = 30

VALID_GENDERS = {"Male", "Female", "Other"}


def intake_missing(patient) -> list[str]:
    """Details a nurse must have checked and recorded for a NEW patient."""
    missing = []
    if not patient.age or patient.age < 1:
        missing.append("age")
    if patient.gender not in VALID_GENDERS:
        missing.append("gender")
    if patient.heart_rate is None:
        missing.append("heart rate")
    if patient.spo2 is None:
        missing.append("SpO2")
    return missing


def slot_holder(db, doctor_id: int, date_str: str, time_str: str):
    return (
        db.query(Appointment)
        .filter(
            Appointment.doctor_id == doctor_id,
            Appointment.appointment_date == date_str,
            Appointment.appointment_time == time_str,
            Appointment.status.in_(SLOT_HOLDING),
        )
        .first()
    )


def _slot_unavailable(doctor, date_str: str, time_str: str) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail=(
            f"Slot not available: {doctor.name} is already booked on "
            f"{date_str} at {time_str}. Please choose another time."
        ),
    )


def get_slots(db, doctor_id: int, date_str: str) -> dict:
    """Slot grid for one doctor on one date, with taken/past slots marked."""
    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if doctor is None:
        raise HTTPException(status_code=404, detail="Doctor not found.")
    try:
        day = datetime.strptime(date_str, "%Y-%m-%d")
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid date. Use YYYY-MM-DD.")

    booked = sorted(
        a.appointment_time
        for a in db.query(Appointment).filter(
            Appointment.doctor_id == doctor_id,
            Appointment.appointment_date == date_str,
            Appointment.status.in_(SLOT_HOLDING),
        )
    )
    current = now()
    slots = []
    t = day.replace(hour=SLOT_START_HOUR, minute=0)
    end = day.replace(hour=SLOT_END_HOUR, minute=0)
    while t < end:
        label = t.strftime("%H:%M")
        if label in booked:
            state = "BOOKED"
        elif t <= current:
            state = "PAST"
        else:
            state = "AVAILABLE"
        slots.append({"time": label, "available": state == "AVAILABLE", "state": state})
        t += timedelta(minutes=SLOT_MINUTES)

    return {"doctor_id": doctor_id, "date": date_str, "booked": booked, "slots": slots}


def _grace() -> timedelta:
    """Minutes after the slot before an un-visited appointment is closed.

    Default 0 = the moment the appointment time passes. Set
    APPOINTMENT_GRACE_MINUTES to give late patients a window.
    """
    try:
        return timedelta(minutes=max(0, int(os.getenv("APPOINTMENT_GRACE_MINUTES", "0"))))
    except ValueError:
        return timedelta(0)


def parse_slot(date_str: str, time_str: str) -> datetime:
    try:
        return datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=400,
            detail="Invalid date/time. Use YYYY-MM-DD and HH:MM.",
        )


def book_appointment(db, data) -> dict:
    patient = db.query(Patient).filter(Patient.id == data.patient_id).first()
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found.")

    doctor = db.query(Doctor).filter(Doctor.id == data.doctor_id).first()
    if doctor is None:
        raise HTTPException(status_code=404, detail="Doctor not found.")

    if not doctor.is_available:
        raise HTTPException(status_code=400, detail="Doctor is currently unavailable.")

    slot = parse_slot(data.appointment_date, data.appointment_time)
    if slot <= now():
        raise HTTPException(
            status_code=400,
            detail="Appointment must be scheduled for a future date and time.",
        )

    date_str = slot.strftime("%Y-%m-%d")
    time_str = slot.strftime("%H:%M")

    if slot_holder(db, doctor.id, date_str, time_str):
        raise _slot_unavailable(doctor, date_str, time_str)

    appointment = Appointment(
        patient_id=patient.id,
        doctor_id=doctor.id,
        appointment_date=date_str,
        appointment_time=time_str,
        reason=data.reason,
        status=SCHEDULED,
    )
    db.add(appointment)
    try:
        db.commit()
    except IntegrityError:
        # Someone else booked the same slot between our check and the insert.
        db.rollback()
        raise _slot_unavailable(doctor, date_str, time_str)
    db.refresh(appointment)

    AuditService.record(
        db=db,
        patient_id=patient.id,
        agent="Appointment Agent",
        action="APPOINTMENT_BOOKED",
        status="EXECUTED",
        details={
            "appointment_id": appointment.id,
            "doctor": doctor.name,
            "date": date_str,
            "time": time_str,
        },
    )

    return {
        "status": SCHEDULED,
        "message": "Appointment booked successfully.",
        "appointment": {
            "id": appointment.id,
            "patient_id": patient.id,
            "patient_code": patient.patient_code,
            "patient_name": patient.name,
            "doctor_id": doctor.id,
            "doctor_name": doctor.name,
            "specialization": doctor.specialization,
            "appointment_date": appointment.appointment_date,
            "appointment_time": appointment.appointment_time,
            "reason": appointment.reason,
            "status": appointment.status,
        },
    }


def expire_appointments(db) -> int:
    """SCHEDULED appointments whose time has passed -> NOT_VISITED.

    A nurse marks a patient as visited when they arrive; anything still
    SCHEDULED once its time (plus optional grace) has passed was a no-show.
    Idempotent: only rows with status SCHEDULED are ever touched.
    """
    current = now()
    grace = _grace()
    expired = []

    for appointment in db.query(Appointment).filter(Appointment.status == SCHEDULED).all():
        try:
            slot = datetime.strptime(
                f"{appointment.appointment_date} {appointment.appointment_time}",
                "%Y-%m-%d %H:%M",
            )
        except ValueError:
            continue
        if current > slot + grace:
            appointment.status = NOT_VISITED
            expired.append(appointment)

    if not expired:
        return 0

    info = [(a.id, a.patient_id, a.appointment_date, a.appointment_time) for a in expired]
    db.commit()

    for appt_id, patient_id, date_str, time_str in info:
        AuditService.record(
            db=db,
            patient_id=patient_id,
            agent="Appointment Agent",
            action="APPOINTMENT_NOT_VISITED",
            status="EXECUTED",
            details={"appointment_id": appt_id, "date": date_str, "time": time_str},
        )
    return len(info)


def mark_visited(db, appointment_id: int, staff_name: str) -> dict:
    """A nurse records that the patient has arrived for a SCHEDULED appointment."""
    # Close out anything already past its time first, so a stale row cannot be
    # marked visited after the slot has been booked as not visited.
    expire_appointments(db)

    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if appointment is None:
        raise HTTPException(status_code=404, detail="Appointment not found.")

    if appointment.status != SCHEDULED:
        raise HTTPException(
            status_code=409,
            detail=f"Appointment is already {appointment.status.replace('_', ' ').lower()}.",
        )

    patient = appointment.patient
    if patient.status == "NEW":
        # A new patient's age, gender, heart rate and SpO2 must be checked and
        # recorded by a nurse before the visit can be confirmed.
        missing = intake_missing(patient)
        if missing:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Nurse intake incomplete: record "
                    + ", ".join(missing)
                    + " before marking this new patient as visited."
                ),
            )
    elif patient.status == "DISCHARGED":
        # A new visit after discharge starts a new episode of care.
        patient.status = "WAITING"

    appointment.status = VISITED
    appointment.visited_at = now()
    appointment.visited_by = staff_name
    db.commit()
    db.refresh(appointment)

    AuditService.record(
        db=db,
        patient_id=appointment.patient_id,
        agent="Appointment Agent",
        action="APPOINTMENT_VISITED",
        status="EXECUTED",
        details={
            "appointment_id": appointment.id,
            "marked_by": staff_name,
            "date": appointment.appointment_date,
            "time": appointment.appointment_time,
        },
    )
    return {
        "status": VISITED,
        "appointment_id": appointment.id,
        "message": "Patient marked as visited.",
    }
