from fastapi import Body, Depends, FastAPI, Header, HTTPException, Response
from sqlalchemy.orm import Session
from app.agents.triage_agent import TriageAgent
from app.schemas.triage import triage_to_dict
from app.agents.imaging_agent import ImagingAgent, MAX_IMAGE_BYTES, detect_mime
import base64
import binascii
import json
from app.database.connection import get_db
from app.models.patient import Patient
from app.core.config import settings
from app.database.init_db import init_database
from app.models import Bed, Department, Doctor, Patient
from app.agents.monitoring_agent import MonitoringAgent
from app.agents.resource_agent import ResourceAgent
from app.services.orchestrator import HelioOrchestrator
from app.services.audit_service import AuditService
from app.models import AuditLog
from app.models import Nurse, Doctor, Patient, Bed
from pydantic import AliasChoices, BaseModel, Field
from app.models.appointment import Appointment
from datetime import datetime
from app.models.models import DiagnosticRequest
from app.models.discharge import DischargeRequest
from app.models.emergency import EmergencyAlert
from app.services import emergency_service
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import os
from app.database.seed import seed_database
from app.core.staff import authenticate, STAFF
from app.agents.discharge_agent import DischargeAgent
from app.core.clock import now as hospital_now
import asyncio
from app.agents.appointment_agent import AppointmentAgent
from app.services.appointment_service import (
    book_appointment,
    expire_appointments,
    get_slots,
    intake_missing,
    mark_visited,
    SCHEDULED,
    CANCELLED,
    AUTO_CANCELLED,
    COMPLETED,
    VISITED,
    NOT_VISITED,
)
from app.core.security import hash_password, normalize_contact, verify_password
from app.database.connection import SessionLocal

# Built React frontend (created by the Dockerfile / `npm run build`).
FRONTEND_DIST = Path(
    os.getenv(
        "FRONTEND_DIST",
        Path(__file__).resolve().parents[2] / "frontend" / "dist",
    )
)

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Helio - Autonomous Multi-Agent Hospital Operations System",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        *[o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
class AppointmentCreate(BaseModel):
    patient_id: int
    doctor_id: int
    appointment_date: str
    appointment_time: str
    reason: str

@app.on_event("startup")
def startup_event():
    init_database()
    # Render's filesystem is ephemeral, so load demo data on a fresh database.
    seed_database()


async def _appointment_expiry_loop():
    """Backend-side expiry: runs regardless of whether any browser is open."""
    while True:
        def _run():
            db = SessionLocal()
            try:
                return expire_appointments(db)
            finally:
                db.close()

        try:
            count = await asyncio.to_thread(_run)
            if count:
                print(f"[Appointment Agent] Marked {count} appointment(s) as not visited")
        except Exception as error:
            print(f"[Appointment Agent] Expiry run failed: {error}")
        await asyncio.sleep(60)


@app.on_event("startup")
async def start_expiry_loop():
    asyncio.create_task(_appointment_expiry_loop())


@app.get("/")
def root():
    if (FRONTEND_DIST / "index.html").exists():
        return FileResponse(FRONTEND_DIST / "index.html")

    return {
        "application": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
    }


class LoginRequest(BaseModel):
    email: str
    password: str


@app.post("/api/auth/login")
def login(credentials: LoginRequest, db: Session = Depends(get_db)):
    member = authenticate(credentials.email, credentials.password)

    if member is None:
        AuditService.record(
            db=db,
            patient_id=None,
            agent="Access Control",
            action="STAFF_LOGIN",
            status="DENIED",
            details={"email": (credentials.email or "").strip().lower()},
        )
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password.",
        )

    AuditService.record(
        db=db,
        patient_id=None,
        agent="Access Control",
        action="STAFF_LOGIN",
        status="EXECUTED",
        details={"email": member["email"], "role": member["role"]},
    )

    return {
        "name": member["name"],
        "email": member["email"],
        "role": member["role"],
    }


def require_doctor(x_staff_email: str | None = Header(default=None)):
    """Server-side gate: only a signed-in Doctor may approve/reject discharge."""
    email = (x_staff_email or "").strip().lower()
    member = next((m for m in STAFF if m["email"] == email), None)
    if member is None or member["role"] != "Doctor":
        raise HTTPException(status_code=403, detail="Only a doctor can approve or reject a discharge.")
    return member


def require_nurse(x_staff_email: str | None = Header(default=None)):
    """Server-side gate: only a signed-in Nurse may mark a patient as visited."""
    email = (x_staff_email or "").strip().lower()
    member = next((m for m in STAFF if m["email"] == email), None)
    if member is None or member["role"] != "Nurse":
        raise HTTPException(status_code=403, detail="Only a nurse can mark a patient as visited.")
    return member


def _staff_by_email(email: str | None):
    email = (email or "").strip().lower()
    return next((m for m in STAFF if m["email"] == email), None)


def require_nurse_for_vitals(x_staff_email: str | None = Header(default=None)):
    """Only a signed-in Nurse may record vitals and symptoms."""
    member = _staff_by_email(x_staff_email)
    if member is None or member["role"] != "Nurse":
        raise HTTPException(status_code=403, detail="Only a nurse can record vitals and symptoms.")
    return member


def require_nurse_for_imaging(x_staff_email: str | None = Header(default=None)):
    """Only a signed-in Nurse may upload diagnostic images."""
    member = _staff_by_email(x_staff_email)
    if member is None or member["role"] != "Nurse":
        raise HTTPException(status_code=403, detail="Only a nurse can upload diagnostic images.")
    return member


class PatientLoginRequest(BaseModel):
    # Existing sign-in: Patient ID + name.
    patient_code: str | None = None
    name: str | None = None
    # Account sign-in: email or phone number + password.
    identifier: str | None = None
    password: str | None = None


def _patient_session(patient: Patient) -> dict:
    return {
        "name": patient.name,
        "email": patient.email or patient.phone or patient.patient_code,
        "role": "Patient",
        "patient_id": patient.id,
        "patient_code": patient.patient_code,
    }


def _find_patient_by_contact(db: Session, kind: str, value: str) -> Patient | None:
    column = Patient.email if kind == "email" else Patient.phone
    return db.query(Patient).filter(column == value).first()


@app.post("/api/auth/patient-login")
def patient_login(credentials: PatientLoginRequest, db: Session = Depends(get_db)):
    # --- email / phone + password ---
    if credentials.identifier is not None:
        try:
            kind, value = normalize_contact(credentials.identifier)
        except ValueError:
            raise HTTPException(status_code=401, detail="Incorrect email/phone or password.")
        patient = _find_patient_by_contact(db, kind, value)
        if patient is None or not verify_password(credentials.password or "", patient.password_hash):
            AuditService.record(
                db=db, patient_id=patient.id if patient else None, agent="Access Control",
                action="PATIENT_LOGIN", status="DENIED", details={"method": kind},
            )
            raise HTTPException(status_code=401, detail="Incorrect email/phone or password.")
        AuditService.record(
            db=db, patient_id=patient.id, agent="Access Control",
            action="PATIENT_LOGIN", status="EXECUTED", details={"method": kind},
        )
        return _patient_session(patient)

    # --- Patient ID + name (dataset patients) ---
    patient = (
        db.query(Patient)
        .filter(Patient.patient_code == (credentials.patient_code or "").strip().upper())
        .first()
    )
    if (
        patient is None
        or patient.name.strip().lower() != (credentials.name or "").strip().lower()
    ):
        AuditService.record(
            db=db, patient_id=patient.id if patient else None, agent="Access Control",
            action="PATIENT_LOGIN", status="DENIED", details={"method": "patient_id"},
        )
        raise HTTPException(status_code=401, detail="Patient ID and name do not match our records.")
    AuditService.record(
        db=db, patient_id=patient.id, agent="Access Control",
        action="PATIENT_LOGIN", status="EXECUTED", details={"method": "patient_id"},
    )
    return _patient_session(patient)


class PatientRegisterRequest(BaseModel):
    name: str
    identifier: str  # email address or phone number
    password: str


@app.post("/api/auth/patient-register")
def patient_register(data: PatientRegisterRequest, db: Session = Depends(get_db)):
    import re as _re

    name = data.name.strip()
    if len(name) < 2:
        raise HTTPException(status_code=400, detail="Please enter your full name.")
    if len(data.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")

    try:
        kind, value = normalize_contact(data.identifier)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))

    if _find_patient_by_contact(db, kind, value) is not None:
        raise HTTPException(
            status_code=409,
            detail=f"An account with this {'email' if kind == 'email' else 'phone number'} already exists. Please sign in.",
        )

    numbers = [
        int(m.group(1))
        for (code,) in db.query(Patient.patient_code).all()
        if (m := _re.fullmatch(r"P(\d+)", code or ""))
    ]
    code = f"P{(max(numbers) if numbers else 0) + 1:03d}"

    patient = Patient(
        patient_code=code,
        name=name,
        age=0,  # not collected at sign-up; shown as "—" until a clinician records it
        gender="Not specified",
        symptoms=None,
        heart_rate=None,
        spo2=None,
        temperature=None,
        status="NEW",
        email=value if kind == "email" else None,
        phone=value if kind == "phone" else None,
        password_hash=hash_password(data.password),
    )
    db.add(patient)
    db.commit()
    db.refresh(patient)

    AuditService.record(
        db=db,
        patient_id=patient.id,
        agent="Patient Portal",
        action="PATIENT_ACCOUNT_CREATED",
        status="EXECUTED",
        details={"patient": patient.patient_code, "signed_up_with": kind},
    )
    return _patient_session(patient)


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "helio-backend",
        "database": "connected",
    }


@app.get("/api/departments")
def get_departments(db: Session = Depends(get_db)):
    departments = db.query(Department).all()

    return [
        {
            "id": department.id,
            "name": department.name,
            "description": department.description,
        }
        for department in departments
    ]


@app.get("/api/doctors")
def get_doctors(db: Session = Depends(get_db)):
    doctors = db.query(Doctor).all()

    return [
        {
            "id": doctor.id,
            "name": doctor.name,
            "specialization": doctor.specialization,
            "department_id": doctor.department_id,
            "staff_code": doctor.staff_code,
            "years_experience": doctor.years_experience,
            "is_available": doctor.is_available,
        }
        for doctor in doctors
    ]


@app.get("/api/nurses")
def get_nurses(db: Session = Depends(get_db)):
    nurses = db.query(Nurse).all()

    return [
        {
            "id": nurse.id,
            "name": nurse.name,
            "department": nurse.department,
            "specialization": nurse.specialization,
            "staff_code": nurse.staff_code,
            "years_experience": nurse.years_experience,
            "is_available": nurse.is_available,
        }
        for nurse in nurses
    ]
@app.patch("/api/doctors/{doctor_id}/availability")
def update_doctor_availability(
    doctor_id: int,
    is_available: bool,
    db: Session = Depends(get_db),
):
    doctor = (
        db.query(Doctor)
        .filter(Doctor.id == doctor_id)
        .first()
    )

    if doctor is None:
        raise HTTPException(
            status_code=404,
            detail="Doctor not found."
        )

    doctor.is_available = is_available

    db.commit()
    db.refresh(doctor)

    AuditService.record(
        db=db,
        patient_id=None,
        agent="Staff Roster",
        action="DOCTOR_AVAILABILITY_CHANGED",
        status="EXECUTED",
        details={"doctor": doctor.name, "is_available": doctor.is_available},
    )

    return {
        "status": "UPDATED",
        "doctor": {
            "id": doctor.id,
            "name": doctor.name,
            "specialization": doctor.specialization,
            "department_id": doctor.department_id,
            "is_available": doctor.is_available,
        },
        "message": (
            f"{doctor.name} is now "
            f"{'available' if doctor.is_available else 'unavailable'}."
        ),
    }

@app.get("/api/patients")
def get_patients(db: Session = Depends(get_db)):
    patients = db.query(Patient).all()

    return [
        {
            "id": patient.id,
            "patient_code": patient.patient_code,
            "name": patient.name,
            "age": patient.age,
            "gender": patient.gender,
            "symptoms": patient.symptoms,
            "heart_rate": patient.heart_rate,
            "spo2": patient.spo2,
            "temperature": patient.temperature,
            "status": patient.status,
            "intake_missing": intake_missing(patient) if patient.status == "NEW" else [],
        }
        for patient in patients
    ]
from pydantic import BaseModel
class PatientCreate(BaseModel):
    patient_code: str
    name: str
    age: int
    gender: str
    symptoms: str
    heart_rate: int = 0
    spo2: float = 0
    temperature: float = 0


@app.post("/api/patients")
def create_patient(
    patient_data: PatientCreate,
    db: Session = Depends(get_db),
):
    existing = (
        db.query(Patient)
        .filter(Patient.patient_code == patient_data.patient_code)
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=400,
            detail="Patient code already exists."
        )

    patient = Patient(
        patient_code=patient_data.patient_code,
        name=patient_data.name,
        age=patient_data.age,
        gender=patient_data.gender,
        symptoms=patient_data.symptoms,
        heart_rate=patient_data.heart_rate,
        spo2=patient_data.spo2,
        temperature=patient_data.temperature,
        status="WAITING",
    )

    db.add(patient)
    db.commit()
    db.refresh(patient)

    return {
        "id": patient.id,
        "patient_code": patient.patient_code,
        "name": patient.name,
        "status": patient.status,
    }
class NewPatientCreate(BaseModel):
    name: str
    age: int
    gender: str
    symptoms: str
    # Vitals are recorded by a nurse (ignored for other roles).
    heart_rate: int | None = None
    spo2: float | None = None
    temperature: float | None = None


class VitalsUpdate(BaseModel):
    heart_rate: int
    spo2: float
    temperature: float
    symptoms: str | None = None
    # Nurse intake for new patients also confirms age and gender.
    age: int | None = None
    gender: str | None = None


VALID_GENDERS = {"Male", "Female", "Other"}


def _validate_vitals(heart_rate, spo2, temperature) -> None:
    """Reject missing or physiologically impossible readings."""
    if heart_rate is None or spo2 is None or temperature is None:
        raise HTTPException(
            status_code=400,
            detail="Heart rate, SpO2 and temperature are required.",
        )
    if not 20 <= heart_rate <= 300:
        raise HTTPException(status_code=400, detail="Heart rate must be between 20 and 300 bpm.")
    if not 50 <= spo2 <= 100:
        raise HTTPException(status_code=400, detail="SpO2 must be between 50 and 100 %.")
    if not 30 <= temperature <= 45:
        raise HTTPException(status_code=400, detail="Temperature must be between 30 and 45 °C.")


def _patient_dict(p: Patient) -> dict:
    return {
        "id": p.id,
        "patient_code": p.patient_code,
        "name": p.name,
        "age": p.age or None,  # 0 = not recorded (self-registered accounts)
        "gender": None if p.gender == "Not specified" else p.gender,
        "symptoms": p.symptoms,
        "heart_rate": p.heart_rate,
        "spo2": p.spo2,
        "temperature": p.temperature,
        "status": p.status,
        # NEW patients need a nurse to check and record these before the visit.
        "intake_missing": intake_missing(p) if p.status == "NEW" else [],
    }


def _ensure_not_discharged(patient: Patient, what: str) -> None:
    if patient.status == "DISCHARGED":
        raise HTTPException(
            status_code=400,
            detail=(
                f"{patient.name} ({patient.patient_code}) has already been discharged. "
                f"{what} cannot be done for a discharged patient."
            ),
        )


@app.get("/api/patients/search")
def search_patients(q: str = "", db: Session = Depends(get_db)):
    term = q.strip()
    if not term:
        return []
    like = f"%{term}%"
    rows = (
        db.query(Patient)
        .filter((Patient.patient_code.ilike(like)) | (Patient.name.ilike(like)))
        .order_by(Patient.patient_code)
        .limit(8)
        .all()
    )
    return [_patient_dict(p) for p in rows]


@app.get("/api/patients/{patient_id}")
def get_patient(patient_id: int, db: Session = Depends(get_db)):
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found.")
    return _patient_dict(patient)


@app.post("/api/patients/new")
def create_new_patient(
    data: NewPatientCreate,
    db: Session = Depends(get_db),
    x_staff_email: str | None = Header(default=None),
):
    import re as _re

    staff = _staff_by_email(x_staff_email)
    is_nurse = staff is not None and staff["role"] == "Nurse"

    if not data.name.strip() or not data.symptoms.strip():
        raise HTTPException(status_code=400, detail="Name and symptoms are required.")
    if data.age < 1 or data.age > 120:
        raise HTTPException(status_code=400, detail="Enter a valid age.")
    if data.gender not in VALID_GENDERS:
        raise HTTPException(status_code=400, detail="Select a gender (Male, Female or Other).")
    if is_nurse:
        _validate_vitals(data.heart_rate, data.spo2, data.temperature)

    numbers = [
        int(m.group(1))
        for (code,) in db.query(Patient.patient_code).all()
        if (m := _re.fullmatch(r"P(\d+)", code or ""))
    ]
    code = f"P{(max(numbers) if numbers else 0) + 1:03d}"

    patient = Patient(
        patient_code=code,
        name=data.name.strip(),
        age=data.age,
        gender=data.gender,
        symptoms=data.symptoms.strip(),
        heart_rate=data.heart_rate if is_nurse else None,
        spo2=data.spo2 if is_nurse else None,
        temperature=data.temperature if is_nurse else None,
        status="NEW",
    )
    db.add(patient)
    db.commit()
    db.refresh(patient)

    AuditService.record(
        db=db,
        patient_id=patient.id,
        agent="Appointment Agent",
        action="PATIENT_REGISTERED",
        status="EXECUTED",
        details={
            "patient": patient.patient_code,
            "vitals_recorded_by": staff["name"] if is_nurse else None,
        },
    )
    return _patient_dict(patient)


@app.patch("/api/patients/{patient_id}/vitals")
def update_patient_vitals(
    patient_id: int,
    data: VitalsUpdate,
    db: Session = Depends(get_db),
    nurse: dict = Depends(require_nurse_for_vitals),
):
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found.")

    _validate_vitals(data.heart_rate, data.spo2, data.temperature)
    if data.symptoms is not None and not data.symptoms.strip():
        raise HTTPException(status_code=400, detail="Symptoms cannot be empty.")

    if data.age is not None and not 1 <= data.age <= 120:
        raise HTTPException(status_code=400, detail="Enter a valid age.")
    if data.gender is not None and data.gender not in VALID_GENDERS:
        raise HTTPException(status_code=400, detail="Select a gender (Male, Female or Other).")

    previous = {
        "heart_rate": patient.heart_rate,
        "spo2": patient.spo2,
        "temperature": patient.temperature,
        "symptoms": patient.symptoms,
        "age": patient.age,
        "gender": patient.gender,
    }
    if data.age is not None:
        patient.age = data.age
    if data.gender is not None:
        patient.gender = data.gender
    patient.heart_rate = data.heart_rate
    patient.spo2 = data.spo2
    patient.temperature = data.temperature
    if data.symptoms is not None:
        patient.symptoms = data.symptoms.strip()
    db.commit()
    db.refresh(patient)

    AuditService.record(
        db=db,
        patient_id=patient.id,
        agent="Nurse",
        action="VITALS_RECORDED",
        status="EXECUTED",
        details={
            "recorded_by": nurse["name"],
            "previous": previous,
            "heart_rate": patient.heart_rate,
            "spo2": patient.spo2,
            "temperature": patient.temperature,
            "age": patient.age,
            "gender": patient.gender,
        },
    )
    if patient.status == "NEW" and not intake_missing(patient):
        AuditService.record(
            db=db,
            patient_id=patient.id,
            agent="Nurse",
            action="INTAKE_VERIFIED",
            status="EXECUTED",
            details={"verified_by": nurse["name"], "patient": patient.patient_code},
        )
    return _patient_dict(patient)


@app.get("/api/beds")
def get_beds(db: Session = Depends(get_db)):
    beds = db.query(Bed).all()

    return [
        {
            "id": bed.id,
            "bed_code": bed.bed_code,
            "ward_type": bed.ward_type,
            "department_id": bed.department_id,
            "is_occupied": bed.is_occupied,
            "patient_id": bed.patient_id,
            "patient_code": (
                db.query(Patient.patient_code).filter(Patient.id == bed.patient_id).scalar()
                if bed.patient_id else None
            ),
        }
        for bed in beds
    ]
@app.get("/api/appointments")
def get_appointments(patient_id: int | None = None, db: Session = Depends(get_db)):
    expire_appointments(db)

    query = db.query(Appointment)
    if patient_id is not None:
        query = query.filter(Appointment.patient_id == patient_id)
    appointments = query.order_by(Appointment.id.desc()).all()

    return [
        {
            "id": a.id,
            "patient_id": a.patient_id,
            "patient_code": a.patient.patient_code,
            "patient_name": a.patient.name,
            "doctor_id": a.doctor_id,
            "doctor_name": a.doctor.name,
            "specialization": a.doctor.specialization,
            "appointment_date": a.appointment_date,
            "appointment_time": a.appointment_time,
            "reason": a.reason,
            "status": a.status,
            "visited_at": a.visited_at.isoformat() if a.visited_at else None,
            "visited_by": a.visited_by,
            "bed_needed": a.bed_needed,
            "bed_code": a.bed_code,
            "bed_decision_by": a.bed_decision_by,
            "patient_status": a.patient.status,
            "intake_missing": intake_missing(a.patient) if a.patient.status == "NEW" else [],
            "patient_age": a.patient.age or None,
            "patient_gender": None if a.patient.gender == "Not specified" else a.patient.gender,
            "heart_rate": a.patient.heart_rate,
            "spo2": a.patient.spo2,
            "temperature": a.patient.temperature,
            "symptoms": a.patient.symptoms,
        }
        for a in appointments
    ]


@app.get("/api/appointments/recommend/{patient_id}")
def recommend_doctor(patient_id: int, db: Session = Depends(get_db)):
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found.")

    doctors = db.query(Doctor).all()
    return AppointmentAgent().recommend(patient, doctors).to_dict()


@app.get("/api/appointments/slots")
def appointment_slots(doctor_id: int, date: str, db: Session = Depends(get_db)):
    """Which slots a doctor has free (or already booked) on a date."""
    return get_slots(db, doctor_id, date)


@app.post("/api/appointments")
def create_appointment(
    appointment_data: AppointmentCreate,
    db: Session = Depends(get_db),
):
    return book_appointment(db, appointment_data)


@app.post("/api/appointments/expire")
def run_appointment_expiry(db: Session = Depends(get_db)):
    return {"auto_cancelled": expire_appointments(db)}


@app.patch("/api/appointments/{appointment_id}/cancel")
def cancel_appointment(
    appointment_id: int,
    db: Session = Depends(get_db),
):
    appointment = (
        db.query(Appointment).filter(Appointment.id == appointment_id).first()
    )
    if appointment is None:
        raise HTTPException(status_code=404, detail="Appointment not found.")

    if appointment.status != SCHEDULED:
        return {
            "status": f"ALREADY_{appointment.status}",
            "message": f"Appointment is already {appointment.status}.",
        }

    appointment.status = CANCELLED
    db.commit()

    AuditService.record(
        db=db,
        patient_id=appointment.patient_id,
        agent="Appointment Agent",
        action="APPOINTMENT_CANCELLED",
        status="EXECUTED",
        details={
            "appointment_id": appointment.id,
            "date": appointment.appointment_date,
            "time": appointment.appointment_time,
        },
    )

    return {
        "status": CANCELLED,
        "appointment_id": appointment.id,
        "message": "Appointment cancelled successfully.",
    }


@app.patch("/api/appointments/{appointment_id}/visited")
def mark_appointment_visited(
    appointment_id: int,
    nurse=Depends(require_nurse),
    db: Session = Depends(get_db),
):
    """A nurse confirms the patient has arrived for their appointment."""
    return mark_visited(db, appointment_id, nurse["name"])


# ============================================================
# AUDIT TRAIL
# ============================================================

def _audit_dict(log: AuditLog, patient_codes: dict[int, str]) -> dict:
    return {
        "id": log.id,
        "patient_id": log.patient_id,
        "patient_code": patient_codes.get(log.patient_id) if log.patient_id else None,
        "agent": log.agent,
        "action": log.action,
        "status": log.status,
        "details": log.details,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


@app.get("/api/audit")
def get_audit_logs(
    agent: str | None = None,
    action: str | None = None,
    patient_id: int | None = None,
    limit: int | None = None,
    db: Session = Depends(get_db),
):
    """Every recorded audit event, newest first (optionally filtered)."""
    query = db.query(AuditLog)
    if agent:
        query = query.filter(AuditLog.agent == agent)
    if action:
        query = query.filter(AuditLog.action == action)
    if patient_id is not None:
        query = query.filter(AuditLog.patient_id == patient_id)
    query = query.order_by(AuditLog.id.desc())
    if limit:
        query = query.limit(max(1, min(limit, 10000)))
    logs = query.all()

    ids = {log.patient_id for log in logs if log.patient_id}
    patient_codes = (
        dict(db.query(Patient.id, Patient.patient_code).filter(Patient.id.in_(ids)).all())
        if ids
        else {}
    )
    return [_audit_dict(log, patient_codes) for log in logs]


# ============================================================
# DIAGNOSTIC REQUESTS
# ============================================================

def _diagnostic_dict(request: DiagnosticRequest) -> dict:
    """List/detail shape. Never includes the raw image bytes."""
    ai_report = None
    if request.ai_report:
        try:
            ai_report = json.loads(request.ai_report)
        except ValueError:
            ai_report = None

    return {
        "id": request.id,
        "patient_id": request.patient_id,
        "patient_name": request.patient.name if request.patient else "Unknown Patient",
        "requested_by": request.requested_by,
        "doctor_name": request.doctor.name if request.doctor else None,
        "test_type": request.test_type,
        "priority": request.priority,
        "status": request.status,
        "result": request.result,
        "requested_at": request.requested_at.isoformat() if request.requested_at else None,
        "completed_at": request.completed_at.isoformat() if request.completed_at else None,
        "has_image": bool(request.image_filename),
        "image_filename": request.image_filename,
        "image_uploaded_by": request.image_uploaded_by,
        "image_uploaded_at": (
            request.image_uploaded_at.isoformat() if request.image_uploaded_at else None
        ),
        "ai_report": (
            {
                "available": bool(request.ai_available),
                "problem": request.ai_problem,
                "reason": request.ai_reason,
                "confidence": request.ai_confidence,
                "urgency": request.ai_urgency,
                "findings": (ai_report or {}).get("findings", []),
                "image_quality": (ai_report or {}).get("image_quality"),
                "recommended_action": (ai_report or {}).get("recommended_action", ""),
                "model": request.ai_model,
                "analysed_at": (
                    request.ai_analysed_at.isoformat() if request.ai_analysed_at else None
                ),
                "disclaimer": (ai_report or {}).get("disclaimer", ""),
                "body_part": (ai_report or {}).get("body_part", ""),
                "body_part_confidence": (ai_report or {}).get("body_part_confidence"),
                "condition": (ai_report or {}).get("condition", ""),
                "condition_confidence": (ai_report or {}).get("condition_confidence"),
                "model_metrics": (ai_report or {}).get("model_metrics", {}),
            }
            if request.ai_analysed_at
            else None
        ),
        "reviewed_by": request.reviewed_by,
    }


@app.get("/api/diagnostics")
def get_diagnostic_requests(
    db: Session = Depends(get_db),
):
    requests = (
        db.query(DiagnosticRequest)
        .order_by(DiagnosticRequest.id.desc())
        .all()
    )
    return [_diagnostic_dict(request) for request in requests]


DIAGNOSTIC_PRIORITIES = {"ROUTINE", "HIGH", "URGENT", "CRITICAL"}


class DiagnosticCreate(BaseModel):
    patient_id: int
    # The UI historically sent "test_name"; accept both spellings.
    test_type: str = Field(validation_alias=AliasChoices("test_type", "test_name"))
    priority: str = "ROUTINE"
    requested_by: int | None = None  # doctor id (optional)


@app.post("/api/diagnostics")
def create_diagnostic_request(
    data: DiagnosticCreate,
    db: Session = Depends(get_db),
):
    test_type = data.test_type.strip()
    if not test_type:
        raise HTTPException(status_code=400, detail="Enter the diagnostic test to request.")

    patient = db.query(Patient).filter(Patient.id == data.patient_id).first()
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found.")
    _ensure_not_discharged(patient, "Diagnosis")

    doctor = None
    if data.requested_by is not None:
        doctor = db.query(Doctor).filter(Doctor.id == data.requested_by).first()
        if doctor is None:
            raise HTTPException(status_code=404, detail="Doctor not found.")

    priority = data.priority.strip().upper()
    if priority not in DIAGNOSTIC_PRIORITIES:
        raise HTTPException(
            status_code=400,
            detail="Invalid priority. Use ROUTINE, HIGH, URGENT or CRITICAL.",
        )

    diagnostic = DiagnosticRequest(
        patient_id=patient.id,
        requested_by=doctor.id if doctor else None,
        test_type=test_type,
        priority=priority,
        status="REQUESTED",
    )
    db.add(diagnostic)
    db.commit()
    db.refresh(diagnostic)

    AuditService.record(
        db=db,
        patient_id=patient.id,
        agent="Diagnostics",
        action="DIAGNOSTIC_REQUESTED",
        status="EXECUTED",
        details={
            "diagnostic_id": diagnostic.id,
            "test": diagnostic.test_type,
            "priority": diagnostic.priority,
            "requested_by": doctor.name if doctor else None,
        },
    )

    return {
        "status": "CREATED",
        "message": f"{test_type} requested for {patient.name}.",
        "diagnostic": {
            "id": diagnostic.id,
            "patient_id": diagnostic.patient_id,
            "patient_name": patient.name,
            "requested_by": diagnostic.requested_by,
            "doctor_name": doctor.name if doctor else None,
            "test_type": diagnostic.test_type,
            "priority": diagnostic.priority,
            "status": diagnostic.status,
            "result": diagnostic.result,
            "requested_at": (
                diagnostic.requested_at.isoformat() if diagnostic.requested_at else None
            ),
        },
    }


@app.patch("/api/diagnostics/{diagnostic_id}/status")
def update_diagnostic_status(
    diagnostic_id: int,
    status: str,
    result: str | None = None,
    db: Session = Depends(get_db),
    x_staff_email: str | None = Header(default=None),
):
    diagnostic = (
        db.query(DiagnosticRequest)
        .filter(DiagnosticRequest.id == diagnostic_id)
        .first()
    )

    if diagnostic is None:
        raise HTTPException(
            status_code=404,
            detail="Diagnostic request not found."
        )

    allowed_statuses = {
        "REQUESTED",
        "SCHEDULED",
        "IN_PROGRESS",
        "AWAITING_REVIEW",
        "COMPLETED",
        "CANCELLED",
    }

    status = status.upper()

    if status not in allowed_statuses:
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid status. "
                "Use REQUESTED, SCHEDULED, IN_PROGRESS, "
                "AWAITING_REVIEW, COMPLETED or CANCELLED."
            ),
        )

    previous_status = diagnostic.status
    diagnostic.status = status

    if result is not None:
        diagnostic.result = result

    if status == "COMPLETED":
        diagnostic.completed_at = datetime.utcnow()
        reviewer = _staff_by_email(x_staff_email)
        if diagnostic.ai_analysed_at and reviewer and reviewer["role"] == "Doctor":
            diagnostic.reviewed_by = reviewer["name"]

    db.commit()
    db.refresh(diagnostic)

    AuditService.record(
        db=db,
        patient_id=diagnostic.patient_id,
        agent="Diagnostics",
        action="DIAGNOSTIC_STATUS_UPDATED",
        status="EXECUTED",
        details={
            "diagnostic_id": diagnostic.id,
            "test": diagnostic.test_type,
            "from": previous_status,
            "to": status,
        },
    )

    return {
        "status": "UPDATED",
        "message": "Diagnostic request updated successfully.",
        "diagnostic": {
            "id": diagnostic.id,
            "patient_id": diagnostic.patient_id,
            "test_type": diagnostic.test_type,
            "priority": diagnostic.priority,
            "status": diagnostic.status,
            "result": diagnostic.result,
            "completed_at": (
                diagnostic.completed_at.isoformat()
                if diagnostic.completed_at
                else None
            ),
        },
    }
class DiagnosticImageUpload(BaseModel):
    filename: str = "image"
    image_base64: str  # raw base64 (a "data:...;base64," prefix is tolerated)


imaging_agent = ImagingAgent()


@app.post("/api/diagnostics/{diagnostic_id}/image")
def upload_diagnostic_image(
    diagnostic_id: int,
    data: DiagnosticImageUpload,
    db: Session = Depends(get_db),
    nurse: dict = Depends(require_nurse_for_imaging),
):
    """Nurse uploads the scan; the Imaging Agent reads it and reports to the doctor."""
    diagnostic = (
        db.query(DiagnosticRequest)
        .filter(DiagnosticRequest.id == diagnostic_id)
        .first()
    )
    if diagnostic is None:
        raise HTTPException(status_code=404, detail="Diagnostic request not found.")
    if diagnostic.status in {"COMPLETED", "CANCELLED"}:
        raise HTTPException(
            status_code=400,
            detail=f"This request is {diagnostic.status.lower()}; images can no longer be added.",
        )
    _ensure_not_discharged(diagnostic.patient, "Diagnosis")

    payload = data.image_base64.split(",", 1)[-1].strip()
    try:
        image_bytes = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="The image could not be read. Try another file.")

    if not image_bytes:
        raise HTTPException(status_code=400, detail="The image file is empty.")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image is too large. Maximum size is 8 MB.")
    mime_type = detect_mime(image_bytes)
    if mime_type is None:
        raise HTTPException(
            status_code=400,
            detail="Unsupported image type. Upload a PNG, JPEG or WEBP file (export DICOM scans as PNG/JPEG first).",
        )

    patient = diagnostic.patient
    result = imaging_agent.analyse(image_bytes, mime_type, diagnostic.test_type, patient)

    now = datetime.utcnow()
    diagnostic.image_filename = (data.filename or "image").strip()[:200]
    diagnostic.image_mime = mime_type
    diagnostic.image_data = image_bytes
    diagnostic.image_uploaded_by = nurse["name"]
    diagnostic.image_uploaded_at = now

    diagnostic.ai_available = result.available
    diagnostic.ai_problem = result.problem[:300]
    diagnostic.ai_reason = result.reason
    diagnostic.ai_confidence = result.confidence
    diagnostic.ai_urgency = result.urgency
    diagnostic.ai_report = result.model_dump_json()
    diagnostic.ai_model = result.model or None
    diagnostic.ai_analysed_at = now
    diagnostic.reviewed_by = None

    diagnostic.status = "AWAITING_REVIEW"
    diagnostic.result = (
        f"AI preliminary reading: {result.problem} "
        f"(confidence {round(result.confidence * 100)}%) - awaiting doctor review"
        if result.available
        else "Image uploaded - AI reading unavailable, awaiting manual doctor review"
    )[:1000]

    db.commit()
    db.refresh(diagnostic)

    AuditService.record(
        db=db,
        patient_id=diagnostic.patient_id,
        agent="Imaging Agent",
        action="DIAGNOSTIC_IMAGE_ANALYSED",
        status="EXECUTED",
        details={
            "diagnostic_id": diagnostic.id,
            "test": diagnostic.test_type,
            "uploaded_by": nurse["name"],
            "ai_available": result.available,
            "problem": result.problem,
            "body_part": result.body_part,
            "condition": result.condition,
            "confidence": result.confidence,
            "urgency": result.urgency,
        },
    )

    return {
        "status": "ANALYSED" if result.available else "UPLOADED",
        "message": (
            "Image analysed. The report is ready for the doctor."
            if result.available
            else "Image saved. AI analysis was unavailable, so a doctor will review it manually."
        ),
        "diagnostic": _diagnostic_dict(diagnostic),
    }


@app.get("/api/diagnostics/{diagnostic_id}/image")
def get_diagnostic_image(diagnostic_id: int, db: Session = Depends(get_db)):
    diagnostic = (
        db.query(DiagnosticRequest)
        .filter(DiagnosticRequest.id == diagnostic_id)
        .first()
    )
    if diagnostic is None or not diagnostic.image_data:
        raise HTTPException(status_code=404, detail="No image for this diagnostic.")
    return Response(
        content=diagnostic.image_data,
        media_type=diagnostic.image_mime or "application/octet-stream",
        headers={"Cache-Control": "private, max-age=300"},
    )


def _discharge_dict(d: DischargeRequest) -> dict:
    p = d.patient
    return {
        "id": d.id,
        "patient_id": d.patient_id,
        "patient_code": p.patient_code if p else None,
        "patient_name": p.name if p else "Unknown",
        "age": p.age if p else None,
        "gender": p.gender if p else None,
        "doctor_id": d.doctor_id,
        "doctor_name": d.doctor.name if d.doctor else None,
        "doctor_specialization": d.doctor.specialization if d.doctor else None,
        "status": d.status,
        "reason": d.reason,
        "instructions": d.instructions,
        "diagnosis": d.diagnosis,
        "medication": d.medication,
        "amount": d.amount,
        "admission_date": d.admission_date,
        "discharge_date": d.discharge_date,
        "approved_by": d.approved_by,
        "created_at": d.created_at,
        "approved_at": d.approved_at,
    }


@app.get("/api/discharges")
def get_discharges(patient_id: int | None = None, db: Session = Depends(get_db)):
    query = db.query(DischargeRequest)
    if patient_id is not None:
        query = query.filter(DischargeRequest.patient_id == patient_id)
    return [_discharge_dict(d) for d in query.order_by(DischargeRequest.id.desc()).all()]


def _draft_discharge(db: Session, patient: Patient, reason: str, doctor_id: int | None = None) -> DischargeRequest:
    if patient.status == "DISCHARGED":
        raise HTTPException(status_code=400, detail="Patient is already discharged.")

    pending = (
        db.query(DischargeRequest)
        .filter(DischargeRequest.patient_id == patient.id, DischargeRequest.status == "PENDING")
        .first()
    )
    if pending:
        raise HTTPException(status_code=409, detail="A discharge summary is already pending for this patient.")

    now = hospital_now()

    admitted = (
        db.query(AuditLog)
        .filter(AuditLog.patient_id == patient.id, AuditLog.action == "BED_ALLOCATION",
                AuditLog.status == "APPROVED_EXECUTED")
        .order_by(AuditLog.id)
        .first()
    )
    admitted_at = admitted.created_at if admitted else None

    doctor = None
    if doctor_id:
        doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if doctor is None and patient.doctor_id:
        doctor = db.query(Doctor).filter(Doctor.id == patient.doctor_id).first()
    if doctor is None:
        last = (
            db.query(Appointment)
            .filter(Appointment.patient_id == patient.id)
            .order_by(Appointment.id.desc())
            .first()
        )
        doctor = last.doctor if last else None
    if doctor is None:
        rec = AppointmentAgent().recommend(patient, db.query(Doctor).all())
        if rec.recommended_doctor:
            doctor = db.query(Doctor).filter(Doctor.id == rec.recommended_doctor["id"]).first()

    draft = DischargeAgent().draft(patient, admitted_at, doctor, now)

    discharge = DischargeRequest(
        patient_id=patient.id,
        doctor_id=draft["doctor_id"],
        status="PENDING",
        reason=reason,
        admission_date=draft["admission_date"],
        discharge_date=draft["discharge_date"],
        diagnosis=draft["diagnosis"],
        medication=draft["medication"],
        amount=None,
    )
    db.add(discharge)
    db.commit()
    db.refresh(discharge)

    AuditService.record(
        db=db, patient_id=patient.id, agent="Discharge Agent",
        action="DISCHARGE_SUMMARY_DRAFTED", status="PENDING_DOCTOR_APPROVAL",
        details={"discharge_id": discharge.id},
    )
    return discharge


@app.post("/api/discharges/draft/{patient_id}")
def draft_discharge_summary(patient_id: int, db: Session = Depends(get_db)):
    """Discharge Agent fills every field automatically except the amount."""
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found.")
    discharge = _draft_discharge(db, patient, reason="Clinically fit for discharge")
    return {"status": "CREATED", "message": "Discharge summary drafted by the Discharge Agent.",
            "discharge": _discharge_dict(discharge)}


@app.post("/api/discharges")
def create_discharge_request(
    patient_id: int,
    reason: str = "Clinically fit for discharge",
    doctor_id: int | None = None,
    instructions: str | None = None,
    db: Session = Depends(get_db),
):
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found.")
    discharge = _draft_discharge(db, patient, reason, doctor_id)
    if instructions:
        discharge.instructions = instructions
        db.commit()
    return {"status": "CREATED", "message": "Discharge request created successfully.",
            "discharge": _discharge_dict(discharge)}


class AmountUpdate(BaseModel):
    amount: float


@app.patch("/api/discharges/{discharge_id}/amount")
def set_discharge_amount(discharge_id: int, data: AmountUpdate, db: Session = Depends(get_db)):
    """Amount is the only field entered by a person (billing/ward staff)."""
    discharge = db.query(DischargeRequest).filter(DischargeRequest.id == discharge_id).first()
    if discharge is None:
        raise HTTPException(status_code=404, detail="Discharge request not found.")
    if discharge.status != "PENDING":
        raise HTTPException(status_code=400, detail="Amount can only be changed while pending.")
    if data.amount < 0:
        raise HTTPException(status_code=400, detail="Amount cannot be negative.")
    discharge.amount = round(data.amount, 2)
    db.commit()

    AuditService.record(
        db=db, patient_id=discharge.patient_id, agent="Discharge Agent",
        action="DISCHARGE_AMOUNT_SET", status="EXECUTED",
        details={"discharge_id": discharge.id, "amount": discharge.amount},
    )
    return _discharge_dict(discharge)


class ApproveBody(BaseModel):
    medication: str | None = None


@app.patch("/api/discharges/{discharge_id}/approve")
def approve_discharge(
    discharge_id: int,
    body: ApproveBody | None = Body(default=None),
    doctor=Depends(require_doctor),
    db: Session = Depends(get_db),
):
    discharge = db.query(DischargeRequest).filter(DischargeRequest.id == discharge_id).first()
    if discharge is None:
        raise HTTPException(status_code=404, detail="Discharge request not found.")
    if discharge.status != "PENDING":
        raise HTTPException(status_code=400, detail="Only pending discharge requests can be approved.")
    if discharge.amount is None:
        raise HTTPException(status_code=400, detail="Enter the bill amount before the doctor approves.")

    if body and body.medication and body.medication.strip():
        discharge.medication = body.medication.strip()

    now = hospital_now()
    discharge.status = "APPROVED"
    discharge.approved_at = datetime.utcnow()
    discharge.discharge_date = now.strftime("%Y-%m-%d")
    discharge.approved_by = doctor["name"]

    patient = db.query(Patient).filter(Patient.id == discharge.patient_id).first()
    if patient:
        patient.status = "DISCHARGED"
        for bed in db.query(Bed).filter(Bed.patient_id == patient.id).all():
            bed.is_occupied = False
            bed.patient_id = None

    db.commit()
    db.refresh(discharge)

    AuditService.record(
        db=db, patient_id=discharge.patient_id, agent="Discharge Agent",
        action="DISCHARGE", status="APPROVED_BY_DOCTOR",
        details={"discharge_id": discharge.id, "approved_by": doctor["name"]},
    )
    return {"status": "APPROVED", "message": "Discharge approved successfully.",
            "discharge": _discharge_dict(discharge)}


@app.patch("/api/discharges/{discharge_id}/reject")
def reject_discharge(
    discharge_id: int,
    doctor=Depends(require_doctor),
    db: Session = Depends(get_db),
):
    discharge = db.query(DischargeRequest).filter(DischargeRequest.id == discharge_id).first()
    if discharge is None:
        raise HTTPException(status_code=404, detail="Discharge request not found.")
    if discharge.status != "PENDING":
        raise HTTPException(status_code=400, detail="Only pending discharge requests can be rejected.")

    discharge.status = "REJECTED"
    discharge.approved_by = doctor["name"]
    db.commit()
    db.refresh(discharge)

    AuditService.record(
        db=db, patient_id=discharge.patient_id, agent="Discharge Agent",
        action="DISCHARGE", status="REJECTED_BY_DOCTOR",
        details={"discharge_id": discharge.id, "rejected_by": doctor["name"]},
    )
    return {"status": "REJECTED", "message": "Discharge request rejected.",
            "discharge": _discharge_dict(discharge)}


@app.get("/api/monitoring/patient/{patient_id}")

def monitor_patient(
    patient_id: int,
    db: Session = Depends(get_db),
):
    patient = (
        db.query(Patient)
        .filter(Patient.id == patient_id)
        .first()
    )

    if patient is None:
        return {
            "error": "Patient not found",
        }

    agent = MonitoringAgent()

    result = agent.evaluate_patient(patient)

    return {
        "agent": "Monitoring Agent",
        "patient_id": result.patient_id,
        "patient_code": result.patient_code,
        "severity": result.severity.value,
        "abnormal_signals": result.abnormal_signals,
        "summary": result.summary,
        "requires_triage": result.requires_triage,
    }
@app.get("/api/triage/patient/{patient_id}")
def triage_patient(
    patient_id: int,
    db: Session = Depends(get_db),
):
    # 1. Find patient
    patient = (
        db.query(Patient)
        .filter(Patient.id == patient_id)
        .first()
    )

    if patient is None:
        return {
            "error": "Patient not found"
        }

    # 2. Run Monitoring Agent first
    monitoring_agent = MonitoringAgent()

    monitoring_result = monitoring_agent.evaluate_patient(
        patient
    )

    # 3. Stop if triage is not required
    if not monitoring_result.requires_triage:
        return {
            "agent": "Triage Agent",
            "patient_id": patient.id,
            "patient_code": patient.patient_code,
            "status": "NOT_REQUIRED",
            "monitoring": {
                "severity": monitoring_result.severity.value,
                "abnormal_signals": monitoring_result.abnormal_signals,
                "summary": monitoring_result.summary,
            },
        }

    # 4. Run Gemini-powered Triage Agent
    try:
        triage_agent = TriageAgent()

        triage_result = triage_agent.assess_patient(
            patient=patient,
            monitoring_result=monitoring_result,
        )

        return {
            "agent": "Triage Agent",
            "patient_id": patient.id,
            "patient_code": patient.patient_code,
            "status": "COMPLETED",
            "monitoring": {
                "severity": monitoring_result.severity.value,
                "abnormal_signals": monitoring_result.abnormal_signals,
                "summary": monitoring_result.summary,
            },
            "triage": triage_to_dict(triage_result),
        }

    except Exception as e:
        return {
            "agent": "Triage Agent",
            "patient_id": patient.id,
            "patient_code": patient.patient_code,
            "status": "ERROR",
            "error": str(e),
        }

def _analyze_bed_need(patient: Patient, db: Session) -> dict:
    """Monitoring -> Triage -> Bed Agent. Read-only: never mutates the DB."""
    monitoring_result = MonitoringAgent().evaluate_patient(patient)

    if not monitoring_result.requires_triage:
        triage_result = TriageAgent().assess_without_escalation(
            patient=patient, monitoring_result=monitoring_result
        )
        priority = triage_result.priority
        triage_data = {**triage_to_dict(triage_result), "status": "NOT_REQUIRED"}
    else:
        triage_result = TriageAgent().assess_patient(
            patient=patient, monitoring_result=monitoring_result
        )
        priority = triage_result.priority
        triage_data = triage_to_dict(triage_result)

    beds = db.query(Bed).all()  # actual bed records; agent checks availability
    allocation = ResourceAgent().allocate_bed(patient=patient, priority=priority, beds=beds)

    return {
        "monitoring": {
            "severity": monitoring_result.severity.value,
            "abnormal_signals": monitoring_result.abnormal_signals,
            "summary": monitoring_result.summary,
        },
        "triage": triage_data,
        "allocation": allocation,
    }


def _current_bed(patient: Patient, db: Session):
    return (
        db.query(Bed)
        .filter(Bed.patient_id == patient.id, Bed.is_occupied == True)
        .first()
    )


@app.get("/api/resource/patient/{patient_id}")
def allocate_resource(patient_id: int, db: Session = Depends(get_db)):
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if patient is None:
        return {"status": "ERROR", "error": "Patient not found"}

    if patient.status == "DISCHARGED":
        return {"status": "ERROR", "error": f"Patient {patient.patient_code} has been discharged."}

    current = _current_bed(patient, db)
    if current is not None:
        return {
            "status": "ERROR",
            "error": f"Patient {patient.patient_code} already occupies bed {current.bed_code}.",
        }

    analysis = _analyze_bed_need(patient, db)
    a = analysis["allocation"]

    return {
        "status": "COMPLETED",
        "patient": {"id": patient.id, "code": patient.patient_code, "name": patient.name},
        "patient_record": _patient_dict(patient),
        "monitoring": analysis["monitoring"],
        "triage": analysis["triage"],
        "resource": {
            "patient_id": patient.patient_code,
            "category": a.category,
            "priority": a.priority,
            "required_ward": a.recommended_ward,
            "recommended_ward": a.recommended_ward,
            "recommended_bed": a.recommended_bed,
            "availability": "AVAILABLE" if a.available else "UNAVAILABLE",
            "available": a.available,
            "approval_required": True,
            "requires_approval": True,
            "human_intervention_required": not a.available,
            "reason": a.reason,
        },
    }


def _execute_bed_allocation(
    db: Session,
    patient: Patient,
    bed_code: str | None = None,
    actor: str | None = None,
    appointment_id: int | None = None,
) -> dict:
    """Allocate the recommended bed. Shared by Bed Management and the post-visit decision."""
    if patient.status == "DISCHARGED":
        return {"status": "ERROR", "error": "Patient has been discharged."}

    if _current_bed(patient, db) is not None:
        return {"status": "ERROR", "error": "Patient already has a bed."}

    # Re-validate against live data at execution time.
    analysis = _analyze_bed_need(patient, db)
    allocation = analysis["allocation"]

    if not allocation.available:
        return {"status": "NO_BED_AVAILABLE", "message": allocation.reason}

    if bed_code and bed_code != allocation.recommended_bed:
        return {
            "status": "RECOMMENDATION_CHANGED",
            "message": (
                f"Bed availability changed. New recommendation: "
                f"{allocation.recommended_bed}. Please review and approve again."
            ),
        }

    selected_bed = db.query(Bed).filter(Bed.bed_code == allocation.recommended_bed).first()
    if selected_bed is None or selected_bed.is_occupied:
        return {
            "status": "BED_NO_LONGER_AVAILABLE",
            "message": "The recommended bed was occupied before approval execution.",
        }

    selected_bed.is_occupied = True
    selected_bed.patient_id = patient.id
    patient.status = "ADMITTED"
    db.commit()

    AuditService.record(
        db=db,
        patient_id=patient.id,
        agent="Resource Agent",
        action="BED_ALLOCATION",
        status="APPROVED_EXECUTED",
        details={
            "bed": selected_bed.bed_code,
            "ward": allocation.recommended_ward,
            "category": allocation.category,
            "patient": patient.patient_code,
            "approved_by": actor,
            "appointment_id": appointment_id,
            "triage_priority": analysis["triage"].get("priority"),
            "triage_confidence": analysis["triage"].get("confidence"),
        },
    )

    return {
        "status": "ALLOCATED",
        "patient": {
            "id": patient.id,
            "code": patient.patient_code,
            "name": patient.name,
            "status": patient.status,
        },
        "allocation": {
            "ward": allocation.recommended_ward,
            "bed": selected_bed.bed_code,
            "occupied": selected_bed.is_occupied,
        },
        "message": f"Bed {selected_bed.bed_code} allocated to {patient.patient_code}.",
    }


@app.post("/api/resource/allocate/{patient_id}")
def approve_bed_allocation(
    patient_id: int,
    bed_code: str | None = None,
    db: Session = Depends(get_db),
):
    """Executed ONLY after a human approves the recommendation."""
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if patient is None:
        return {"status": "ERROR", "error": "Patient not found"}

    return _execute_bed_allocation(db, patient, bed_code)


# ------------------------------------------------------------
# Post-visit bed decision: after a nurse marks a patient as visited,
# the nurse records whether a bed is needed and, if so, allocates one.
# ------------------------------------------------------------

class BedDecision(BaseModel):
    bed_needed: bool
    bed_code: str | None = None  # the bed the nurse was shown and approved


def _visited_appointment(db: Session, appointment_id: int) -> Appointment:
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if appointment is None:
        raise HTTPException(status_code=404, detail="Appointment not found.")
    if appointment.status != VISITED:
        raise HTTPException(
            status_code=409,
            detail="A bed decision can only be made after the patient is marked as visited.",
        )
    if appointment.patient.status == "DISCHARGED":
        raise HTTPException(
            status_code=409,
            detail="This patient has already been discharged; no bed can be allocated.",
        )
    return appointment


@app.get("/api/appointments/{appointment_id}/bed-recommendation")
def appointment_bed_recommendation(
    appointment_id: int,
    nurse: dict = Depends(require_nurse),
    db: Session = Depends(get_db),
):
    """Triage (with confidence) + Bed Agent recommendation. Read-only."""
    appointment = _visited_appointment(db, appointment_id)
    patient = appointment.patient

    current = _current_bed(patient, db)
    if current is not None:
        return {
            "status": "ALREADY_ALLOCATED",
            "bed": current.bed_code,
            "patient": _patient_dict(patient),
        }

    analysis = _analyze_bed_need(patient, db)
    a = analysis["allocation"]
    return {
        "status": "COMPLETED",
        "appointment_id": appointment.id,
        "patient": _patient_dict(patient),
        "monitoring": analysis["monitoring"],
        "triage": analysis["triage"],
        "resource": {
            "category": a.category,
            "priority": a.priority,
            "required_ward": a.recommended_ward,
            "recommended_bed": a.recommended_bed,
            "available": a.available,
            "reason": a.reason,
        },
    }


@app.post("/api/appointments/{appointment_id}/bed-decision")
def decide_appointment_bed(
    appointment_id: int,
    data: BedDecision,
    nurse: dict = Depends(require_nurse),
    db: Session = Depends(get_db),
):
    appointment = _visited_appointment(db, appointment_id)
    patient = appointment.patient

    if appointment.bed_needed is False or appointment.bed_code:
        raise HTTPException(
            status_code=409,
            detail="A bed decision has already been recorded for this visit.",
        )

    if not data.bed_needed:
        appointment.bed_needed = False
        appointment.bed_decision_by = nurse["name"]
        appointment.bed_decision_at = hospital_now()
        db.commit()
        AuditService.record(
            db=db,
            patient_id=patient.id,
            agent="Nurse",
            action="BED_NOT_NEEDED",
            status="EXECUTED",
            details={"appointment_id": appointment.id, "decided_by": nurse["name"]},
        )
        return {"status": "NO_BED_NEEDED", "message": "Recorded: no bed needed for this visit."}

    result = _execute_bed_allocation(
        db, patient, data.bed_code, actor=nurse["name"], appointment_id=appointment.id
    )

    if result["status"] in ("ALLOCATED", "NO_BED_AVAILABLE"):
        # Either way the nurse has decided a bed is needed; keep that on record
        # (a full ward stays "needed, no bed yet" so the nurse can retry).
        appointment.bed_needed = True
        appointment.bed_decision_by = nurse["name"]
        appointment.bed_decision_at = hospital_now()
        if result["status"] == "ALLOCATED":
            appointment.bed_code = result["allocation"]["bed"]
        db.commit()
    return result


@app.post("/api/resource/reject/{patient_id}")
def reject_bed_allocation(
    patient_id: int,
    bed_code: str | None = None,
    db: Session = Depends(get_db),
):
    """Human rejected the recommendation: no allocation, audit only."""
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if patient is None:
        return {"status": "ERROR", "error": "Patient not found"}

    AuditService.record(
        db=db,
        patient_id=patient.id,
        agent="Resource Agent",
        action="BED_ALLOCATION",
        status="REJECTED",
        details={"bed": bed_code, "patient": patient.patient_code},
    )
    return {"status": "REJECTED", "message": "Bed allocation rejected. No changes were made."}


@app.get("/api/helio/patient/{patient_id}")
def run_helio(
    patient_id: int,
    db: Session = Depends(get_db),
):

    patient = (
        db.query(Patient)
        .filter(Patient.id == patient_id)
        .first()
    )

    if patient is None:
        return {
            "status": "ERROR",
            "error": "Patient not found",
        }

    # -----------------------------------------
    # Get available beds
    # -----------------------------------------

    beds = (
        db.query(Bed)
        .filter(Bed.is_occupied == False)
        .all()
    )

    # -----------------------------------------
    # Run complete agent workflow
    # -----------------------------------------

    orchestrator = HelioOrchestrator()

    result = orchestrator.process_patient(
        patient=patient,
        beds=beds,
    )

    # -----------------------------------------
    # Audit the workflow
    # -----------------------------------------

    AuditService.record(
        db=db,
        patient_id=patient.id,
        agent="Orchestrator",
        action="CARE_FLOW_EXECUTION",
        status=(
            "APPROVAL_REQUIRED"
            if result["requires_approval"]
            else "AUTO"
        ),
        details={
            "priority": result["triage"].priority,
            "triage_confidence": result["triage"].confidence,
            "recommended_bed": (
                result["resource"].recommended_bed
            ),
        },
    )

    # -----------------------------------------
    # Return structured result
    # -----------------------------------------

    return {
        "status": "COMPLETED",

        "patient": {
            "id": patient.id,
            "code": patient.patient_code,
            "name": patient.name,
        },

        "monitoring": {
            "severity":
                result["monitoring"].severity.value,

            "abnormal_signals":
                result["monitoring"].abnormal_signals,

            "summary":
                result["monitoring"].summary,
        },

        "triage": triage_to_dict(result["triage"]),

        "risk":
            result["risk"].to_dict(),

        "resource": {
            "ward":
                result["resource"].recommended_ward,

            "bed":
                result["resource"].recommended_bed,

            "available":
                result["resource"].available,

            "requires_approval":
                result["resource"].requires_approval,

            "reason":
                result["resource"].reason,
        },

        "requires_approval":
            result["requires_approval"],

        "handoff":
            result["handoff"],
    }

@app.get("/api/stats")
def get_hospital_stats(db: Session = Depends(get_db)):

    total_patients = db.query(Patient).count()

    critical_patients = (
        db.query(Patient)
        .filter(Patient.status == "CRITICAL")
        .count()
    )

    warning_patients = (
        db.query(Patient)
        .filter(Patient.status == "WARNING")
        .count()
    )

    available_beds = (
        db.query(Bed)
        .filter(Bed.is_occupied == False)
        .count()
    )

    total_beds = db.query(Bed).count()

    available_doctors = (
        db.query(Doctor)
        .filter(Doctor.is_available == True)
        .count()
    )

    total_doctors = db.query(Doctor).count()

    available_nurses = (
        db.query(Nurse)
        .filter(Nurse.is_available == True)
        .count()
    )

    total_nurses = db.query(Nurse).count()

    return {
    "total_patients": total_patients,
    "critical_patients": critical_patients,
    "warning_patients": warning_patients,
    "available_beds": available_beds,
    "total_beds": total_beds,
    "available_doctors": available_doctors,
    "total_doctors": total_doctors,
    "available_nurses": available_nurses,
    "total_nurses": total_nurses,

    # Keep old nested structure too
    "patients": {
        "total": total_patients,
        "critical": critical_patients,
        "warning": warning_patients,
    },
    "beds": {
        "available": available_beds,
        "total": total_beds,
    },
    "doctors": {
        "available": available_doctors,
        "total": total_doctors,
    },
    "nurses": {
        "available": available_nurses,
        "total": total_nurses,
    },
}
@app.get("/api/doctors/available")
def get_available_doctors(db: Session = Depends(get_db)):

    doctors = (
        db.query(Doctor)
        .filter(Doctor.is_available == True)
        .all()
    )

    return [
        {
            "id": doctor.id,
            "name": doctor.name,
            "specialization": doctor.specialization,
            "available": doctor.is_available,
            "is_available": doctor.is_available,
        }
        for doctor in doctors
    ]
@app.get("/api/nurses/available")
def get_available_nurses(db: Session = Depends(get_db)):

    nurses = (
        db.query(Nurse)
        .filter(Nurse.is_available == True)
        .all()
    )

    return [
        {
            "id": nurse.id,
            "name": nurse.name,
            "department": nurse.department,
            "specialization": nurse.specialization,
            "available": nurse.is_available,
        }
        for nurse in nurses
    ]
@app.post("/api/patients/{patient_id}/assign-doctor/{doctor_id}")
def assign_doctor(
    patient_id: int,
    doctor_id: int,
    db: Session = Depends(get_db),
):
    patient = db.query(Patient).filter(
        Patient.id == patient_id
    ).first()

    if not patient:
        raise HTTPException(
            status_code=404,
            detail="Patient not found."
        )

    doctor = db.query(Doctor).filter(
        Doctor.id == doctor_id
    ).first()

    if not doctor:
        raise HTTPException(
            status_code=404,
            detail="Doctor not found."
        )

    if not doctor.is_available:
        raise HTTPException(
            status_code=400,
            detail="Doctor is currently unavailable."
        )

    patient.doctor_id = doctor.id

    db.commit()
    db.refresh(patient)

    AuditService.record(
        db=db,
        patient_id=patient.id,
        agent="Appointment Agent",
        action="DOCTOR_ASSIGNED",
        status="EXECUTED",
        details={"patient": patient.patient_code, "doctor": doctor.name},
    )

    return {
        "status": "ASSIGNED",
        "patient_id": patient.id,
        "patient_code": patient.patient_code,
        "doctor": {
            "id": doctor.id,
            "name": doctor.name,
            "specialty": doctor.specialization,
        },
    }
# ---------------------------------------------------------------------------
# Emergency alarm: a nurse pages the doctors on call for a critical arrival.
# ---------------------------------------------------------------------------

class EmergencyAlertCreate(BaseModel):
    emergency_type: str
    patient_label: str = ""
    location: str = ""
    notes: str = ""


def require_nurse_for_emergency(x_staff_email: str | None = Header(default=None)):
    member = _staff_by_email(x_staff_email)
    if member is None or member["role"] != "Nurse":
        raise HTTPException(status_code=403, detail="Only a nurse can raise an emergency alert.")
    return member


def require_doctor_for_emergency(x_staff_email: str | None = Header(default=None)):
    member = _staff_by_email(x_staff_email)
    if member is None or member["role"] != "Doctor":
        raise HTTPException(status_code=403, detail="Only a doctor can respond to an emergency alert.")
    return member


def _doctor_for_staff(db: Session, member: dict):
    """Match a signed-in staff account to its row in the doctors table."""
    wanted = member["name"].strip().lower()
    return next(
        (d for d in db.query(Doctor).all() if d.name.strip().lower() == wanted),
        None,
    )


def _paged_ids(alert: EmergencyAlert) -> set[int]:
    try:
        return {int(d["id"]) for d in json.loads(alert.paged_doctors or "[]")}
    except (ValueError, KeyError, TypeError):
        return set()


@app.get("/api/emergency/types")
def get_emergency_types():
    return emergency_service.list_types()


@app.get("/api/emergency/route")
def preview_emergency_route(emergency_type: str, db: Session = Depends(get_db)):
    """Which doctors would be paged for this emergency type (preview only)."""
    if emergency_type not in emergency_service.EMERGENCY_TYPES:
        raise HTTPException(status_code=400, detail="Unknown emergency type.")

    specialty, doctors = emergency_service.route(emergency_type, db.query(Doctor).all())
    return {
        "specialty": specialty,
        "doctors": [emergency_service.doctor_summary(d) for d in doctors],
    }


@app.post("/api/emergency/alerts")
def raise_emergency_alert(
    data: EmergencyAlertCreate,
    db: Session = Depends(get_db),
    nurse: dict = Depends(require_nurse_for_emergency),
):
    config = emergency_service.EMERGENCY_TYPES.get(data.emergency_type)
    if config is None:
        raise HTTPException(status_code=400, detail="Choose the type of emergency.")

    specialty, doctors = emergency_service.route(data.emergency_type, db.query(Doctor).all())
    if not doctors:
        raise HTTPException(
            status_code=409,
            detail=(
                f"No {specialty} doctor is available right now. "
                "Call the emergency desk directly."
            ),
        )

    alert = EmergencyAlert(
        emergency_type=data.emergency_type,
        emergency_label=config["label"],
        required_specialty=specialty,
        patient_label=(data.patient_label or "").strip()[:150] or "Unidentified patient",
        location=(data.location or "").strip()[:120] or None,
        notes=(data.notes or "").strip()[:1000] or None,
        paged_doctors=json.dumps([emergency_service.doctor_summary(d) for d in doctors]),
        status="ACTIVE",
        raised_by=nurse["name"],
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)

    AuditService.record(
        db=db,
        patient_id=None,
        agent="Emergency Alarm",
        action="EMERGENCY_ALERT_RAISED",
        status="EXECUTED",
        details={
            "alert_id": alert.id,
            "type": alert.emergency_label,
            "patient": alert.patient_label,
            "raised_by": nurse["name"],
            "paged": [d.name for d in doctors],
        },
    )

    return emergency_service.alert_dict(alert)


@app.get("/api/emergency/alerts")
def list_emergency_alerts(limit: int = 10, db: Session = Depends(get_db)):
    """Recent alerts (newest first) so the nurse can see who has responded."""
    alerts = (
        db.query(EmergencyAlert)
        .order_by(EmergencyAlert.id.desc())
        .limit(max(1, min(limit, 50)))
        .all()
    )
    return [emergency_service.alert_dict(a) for a in alerts]


@app.get("/api/emergency/alerts/mine")
def my_emergency_alerts(
    db: Session = Depends(get_db),
    doctor_member: dict = Depends(require_doctor_for_emergency),
):
    """Active alerts that page the signed-in doctor. The siren polls this."""
    doctor = _doctor_for_staff(db, doctor_member)
    if doctor is None:
        return []

    active = (
        db.query(EmergencyAlert)
        .filter(EmergencyAlert.status == "ACTIVE")
        .order_by(EmergencyAlert.id.desc())
        .all()
    )
    return [emergency_service.alert_dict(a) for a in active if doctor.id in _paged_ids(a)]


@app.patch("/api/emergency/alerts/{alert_id}/acknowledge")
def acknowledge_emergency_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    doctor_member: dict = Depends(require_doctor_for_emergency),
):
    alert = db.query(EmergencyAlert).filter(EmergencyAlert.id == alert_id).first()
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found.")

    doctor = _doctor_for_staff(db, doctor_member)
    if doctor is None or doctor.id not in _paged_ids(alert):
        raise HTTPException(status_code=403, detail="This alert was not sent to you.")

    if alert.status != "ACTIVE":
        # Someone else already answered (or it was cancelled): not an error for the UI.
        return emergency_service.alert_dict(alert)

    alert.status = "ACKNOWLEDGED"
    alert.acknowledged_by = doctor.name
    alert.acknowledged_at = emergency_service.now()
    db.commit()
    db.refresh(alert)

    AuditService.record(
        db=db,
        patient_id=None,
        agent="Emergency Alarm",
        action="EMERGENCY_ALERT_ACKNOWLEDGED",
        status="EXECUTED",
        details={"alert_id": alert.id, "doctor": doctor.name, "patient": alert.patient_label},
    )

    return emergency_service.alert_dict(alert)


@app.patch("/api/emergency/alerts/{alert_id}/cancel")
def cancel_emergency_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    nurse: dict = Depends(require_nurse_for_emergency),
):
    alert = db.query(EmergencyAlert).filter(EmergencyAlert.id == alert_id).first()
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found.")

    if alert.status != "ACTIVE":
        return emergency_service.alert_dict(alert)

    alert.status = "CANCELLED"
    alert.cancelled_at = emergency_service.now()
    db.commit()
    db.refresh(alert)

    AuditService.record(
        db=db,
        patient_id=None,
        agent="Emergency Alarm",
        action="EMERGENCY_ALERT_CANCELLED",
        status="EXECUTED",
        details={"alert_id": alert.id, "cancelled_by": nurse["name"]},
    )

    return emergency_service.alert_dict(alert)


@app.get("/api")
def api_status():
    return {
        "status": "ok",
        "service": "Helio API",
        "message": "Backend is running"
    }


# ---------------------------------------------------------------------------
# Serve the built frontend (single-service deployment).
# Must stay at the bottom so every /api route above takes priority.
# ---------------------------------------------------------------------------
if (FRONTEND_DIST / "assets").exists():
    app.mount(
        "/assets",
        StaticFiles(directory=FRONTEND_DIST / "assets"),
        name="assets",
    )


@app.get("/{full_path:path}", include_in_schema=False)
def serve_frontend(full_path: str):
    if full_path.startswith("api"):
        raise HTTPException(status_code=404, detail="Not found")

    index_file = FRONTEND_DIST / "index.html"

    if not index_file.exists():
        raise HTTPException(status_code=404, detail="Frontend not built")

    requested = (FRONTEND_DIST / full_path).resolve()

    if (
        full_path
        and requested.is_file()
        and FRONTEND_DIST.resolve() in requested.parents
    ):
        return FileResponse(requested)

    return FileResponse(index_file)
