import csv
from pathlib import Path

from sqlalchemy.orm import Session

from app.database.connection import SessionLocal
from app.database.init_db import init_database
from app.models import Bed, Department, Doctor, Nurse, Patient

DATA_DIR = Path(__file__).resolve().parent / "data"
PATIENT_CSV = DATA_DIR / "patient_vitals_with_symptoms.csv"
STAFF_CSV = DATA_DIR / "doctors_and_nurses.csv"

# Dataset status -> status values the Helio dashboard already understands.
STATUS_MAP = {
    "critical": "CRITICAL",
    "abnormal": "WARNING",
    "normal": "WAITING",
}


# Doctor specialization -> hospital department (default: General Medicine).
DOCTOR_DEPARTMENT = {
    "Emergency & Urgent Care": "Emergency",
    "Critical Care": "Emergency",
    "Anesthesiology": "Emergency",
    "Orthopaedics": "Emergency",
    "Neurology & Neurosurgery": "Emergency",
    "General Surgery": "Emergency",
    "Plastic Surgery": "Emergency",
    "Vascular Surgery": "Emergency",
    "Cardiology": "Cardiology",
}

# Nurse specialization -> hospital department (default: General Medicine).
NURSE_DEPARTMENT = {
    "Emergency Nursing": "Emergency",
    "ICU Nursing": "Cardiology",
    "Cardiac Care Nursing": "Cardiology",
}


def load_staff_from_csv(departments: dict) -> tuple[list[Doctor], list[Nurse]]:
    """Build Doctor and Nurse rows from doctors_and_nurses.csv.

    The CSV has no availability column, so every 5th person is marked
    unavailable to keep the availability toggles meaningful in the demo.
    """
    doctors: list[Doctor] = []
    nurses: list[Nurse] = []

    with open(STAFF_CSV, newline="", encoding="utf-8-sig") as handle:
        for index, row in enumerate(csv.DictReader(handle)):
            role = row["Role"].strip().lower()
            name = row["Name"].strip()
            specialization = row["Specialization"].strip()
            years = int(row["Years of Experience"])
            code = row["Staff ID"].strip()
            available = index % 5 != 4

            if role == "doctor":
                department = DOCTOR_DEPARTMENT.get(specialization, "General Medicine")
                doctors.append(
                    Doctor(
                        name=f"Dr. {name}",
                        specialization=specialization,
                        department_id=departments[department].id,
                        staff_code=code,
                        years_experience=years,
                        is_available=available,
                    )
                )
            elif role == "nurse":
                nurses.append(
                    Nurse(
                        name=name,
                        department=NURSE_DEPARTMENT.get(specialization, "General Medicine"),
                        specialization=specialization,
                        staff_code=code,
                        years_experience=years,
                        is_available=available,
                    )
                )

    return doctors, nurses


def sync_staff_specializations() -> None:
    """Bring an existing database in line with doctors_and_nurses.csv.

    seed_database() skips a database that already has data, so doctors whose
    specialization changed in the CSV (or new doctors added to it) would never
    show up. This updates specialization/name/experience by staff code and adds
    missing doctors. Availability is left alone.
    """
    db: Session = SessionLocal()
    try:
        departments = {d.name: d for d in db.query(Department).all()}
        if not departments:
            return
        existing = {d.staff_code: d for d in db.query(Doctor).all() if d.staff_code}
        changed = False

        with open(STAFF_CSV, newline="", encoding="utf-8-sig") as handle:
            for index, row in enumerate(csv.DictReader(handle)):
                if row["Role"].strip().lower() != "doctor":
                    continue
                code = row["Staff ID"].strip()
                name = f"Dr. {row['Name'].strip()}"
                specialization = row["Specialization"].strip()
                years = int(row["Years of Experience"])
                department = departments.get(
                    DOCTOR_DEPARTMENT.get(specialization, "General Medicine")
                )
                if department is None:
                    continue

                doctor = existing.get(code)
                if doctor is None:
                    db.add(
                        Doctor(
                            name=name,
                            specialization=specialization,
                            department_id=department.id,
                            staff_code=code,
                            years_experience=years,
                            is_available=index % 5 != 4,
                        )
                    )
                    changed = True
                elif (
                    doctor.specialization != specialization
                    or doctor.name != name
                    or doctor.years_experience != years
                    or doctor.department_id != department.id
                ):
                    doctor.name = name
                    doctor.specialization = specialization
                    doctor.years_experience = years
                    doctor.department_id = department.id
                    changed = True

        if changed:
            db.commit()
    finally:
        db.close()


def load_patients_from_csv() -> list[Patient]:
    patients: list[Patient] = []

    with open(PATIENT_CSV, newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            patients.append(
                Patient(
                    patient_code=row["Patient ID"].strip(),
                    name=row["Name"].strip(),
                    age=int(row["Age"]),
                    gender=row["Gender"].strip(),
                    symptoms=row["Symptoms"].strip(),
                    heart_rate=int(round(float(row["Heart Rate (bpm)"]))),
                    spo2=float(row["SPO2"]),
                    temperature=float(row["Temperature (°C)"]),
                    status=STATUS_MAP.get(row["Status"].strip().lower(), "WAITING"),
                )
            )

    return patients


def seed_database():
    # Make sure tables exist
    init_database()

    db: Session = SessionLocal()

    try:
        # Prevent duplicate seed data
        if db.query(Department).first():
            print("Database already contains data.")
            print("Skipping seed operation.")
            db.close()
            sync_staff_specializations()
            return

        # ---------------------------------------------------------
        # 1. DEPARTMENTS
        # ---------------------------------------------------------

        emergency = Department(
            name="Emergency",
            description="Emergency and critical care services",
        )
        cardiology = Department(
            name="Cardiology",
            description="Heart and cardiovascular care",
        )
        general_medicine = Department(
            name="General Medicine",
            description="General medical consultation and treatment",
        )

        db.add_all([emergency, cardiology, general_medicine])
        db.flush()

        departments = {
            "Emergency": emergency,
            "Cardiology": cardiology,
            "General Medicine": general_medicine,
        }

        # ---------------------------------------------------------
        # 2. DOCTORS AND NURSES  (from doctors_and_nurses.csv)
        # ---------------------------------------------------------

        doctors, nurses = load_staff_from_csv(departments)

        db.add_all(doctors)
        db.add_all(nurses)

        # ---------------------------------------------------------
        # 3. PATIENTS  (from patient_vitals_with_symptoms.csv)
        # ---------------------------------------------------------

        patients = load_patients_from_csv()
        db.add_all(patients)
        db.flush()

        # ---------------------------------------------------------
        # 4. BEDS - 100 in total (ICU 20, ER 30, General Medicine 50).
        #    Occupied beds are linked to real patients from the dataset.
        # ---------------------------------------------------------

        critical = [p for p in patients if p.status == "CRITICAL"]
        warning = [p for p in patients if p.status == "WARNING"]
        normal = [p for p in patients if p.status == "WAITING"]

        def build_ward(prefix, ward, department, size, occupants):
            rows = []
            for number in range(1, size + 1):
                occupant = occupants[number - 1] if number <= len(occupants) else None
                rows.append(
                    Bed(
                        bed_code=f"{prefix}-{number:02d}",
                        ward_type=ward,
                        department_id=department.id,
                        is_occupied=occupant is not None,
                        patient_id=occupant.id if occupant else None,
                    )
                )
            return rows

        beds = []
        beds += build_ward("ICU", "ICU", cardiology, 20, critical[:14])
        beds += build_ward("ER", "Emergency", emergency, 30, warning[:18])
        beds += build_ward("GM", "General Medicine", general_medicine, 50, normal[:26])

        db.add_all(beds)

        db.commit()

        print()
        print("=" * 50)
        print("HELIO DATABASE SEEDED SUCCESSFULLY")
        print("=" * 50)
        print(f"Departments : {len(departments)}")
        print(f"Doctors     : {len(doctors)}")
        print(f"Nurses      : {len(nurses)}")
        print(f"Beds        : {len(beds)}")
        print(f"Patients    : {len(patients)}")
        print("=" * 50)

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
