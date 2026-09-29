"""End-to-end checks for the nurse-intake / bed-decision / slot / discharge / triage-confidence changes.

Run:  python -m pytest test_workflow_changes.py -q
"""
import os
import tempfile
from datetime import timedelta

_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DATABASE_URL"] = f"sqlite:///{_db.name}"

import pytest
from fastapi.testclient import TestClient

from app.core.clock import now
from app.database.connection import SessionLocal
from app.main import app
from app.models import Patient

NURSE = {"X-Staff-Email": "tahseen@gmail.com"}
DOCTOR = {"X-Staff-Email": "eva@gmail.com"}
TOMORROW = (now() + timedelta(days=1)).strftime("%Y-%m-%d")


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _doctor_id(client):
    return next(d["id"] for d in client.get("/api/doctors").json() if d["is_available"])


def _new_patient(client, **over):
    body = {"name": "Test Person", "age": 40, "gender": "Female", "symptoms": "chest pain"}
    body.update(over)
    r = client.post("/api/patients/new", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _book(client, patient_id, doctor_id, time):
    return client.post("/api/appointments", json={
        "patient_id": patient_id, "doctor_id": doctor_id,
        "appointment_date": TOMORROW, "appointment_time": time, "reason": "checkup",
    })


def test_1_new_patient_needs_nurse_intake_before_visit(client):
    doc = _doctor_id(client)
    p = _new_patient(client)  # registered without vitals (not a nurse)
    assert set(p["intake_missing"]) == {"heart rate", "SpO2"}
    listed = next(x for x in client.get("/api/patients").json() if x["id"] == p["id"])
    assert set(listed["intake_missing"]) == {"heart rate", "SpO2"}  # feeds the "awaiting intake" panel

    appt = _book(client, p["id"], doc, "09:00").json()["appointment"]
    r = client.patch(f"/api/appointments/{appt['id']}/visited", headers=NURSE)
    assert r.status_code == 409 and "heart rate" in r.json()["detail"]

    # nurse checks and records the details (also confirming age and gender)
    r = client.patch(f"/api/patients/{p['id']}/vitals", headers=NURSE, json={
        "heart_rate": 88, "spo2": 97, "temperature": 37.0, "age": 41, "gender": "Female"})
    assert r.status_code == 200 and r.json()["intake_missing"] == []
    assert r.json()["age"] == 41

    assert client.patch(f"/api/appointments/{appt['id']}/visited", headers=NURSE).status_code == 200
    # doctors cannot record vitals
    assert client.patch(f"/api/patients/{p['id']}/vitals", headers=DOCTOR, json={
        "heart_rate": 80, "spo2": 98, "temperature": 37}).status_code == 403


def test_4_double_booking_shows_slot_not_available(client):
    doc = _doctor_id(client)
    a, b = _new_patient(client), _new_patient(client)
    assert _book(client, a["id"], doc, "11:00").status_code == 200

    r = _book(client, b["id"], doc, "11:00")
    assert r.status_code == 409 and r.json()["detail"].startswith("Slot not available")

    slots = client.get("/api/appointments/slots", params={"doctor_id": doc, "date": TOMORROW}).json()
    assert "11:00" in slots["booked"]
    assert next(s for s in slots["slots"] if s["time"] == "11:00")["state"] == "BOOKED"
    assert next(s for s in slots["slots"] if s["time"] == "12:00")["available"] is True

    # cancelling frees the slot again
    appt_id = next(x["id"] for x in client.get("/api/appointments").json()
                   if x["patient_id"] == a["id"] and x["appointment_time"] == "11:00")
    client.patch(f"/api/appointments/{appt_id}/cancel")
    assert _book(client, b["id"], doc, "11:00").status_code == 200


def test_2_and_5_bed_decision_after_visit_with_triage_confidence(client):
    doc = _doctor_id(client)
    p = _new_patient(client, symptoms="breathlessness")
    client.patch(f"/api/patients/{p['id']}/vitals", headers=NURSE, json={
        "heart_rate": 135, "spo2": 88, "temperature": 38.5})
    appt = _book(client, p["id"], doc, "13:00").json()["appointment"]

    # bed decision is not possible before the visit
    assert client.get(f"/api/appointments/{appt['id']}/bed-recommendation", headers=NURSE).status_code == 409
    client.patch(f"/api/appointments/{appt['id']}/visited", headers=NURSE)

    rec = client.get(f"/api/appointments/{appt['id']}/bed-recommendation", headers=NURSE).json()
    t = rec["triage"]
    assert 0 <= t["confidence"] <= 1 and t["confidence_pct"] == round(t["confidence"] * 100)
    assert t["confidence_level"] in {"HIGH", "MEDIUM", "LOW"} and t["confidence_factors"]
    assert rec["resource"]["available"] and rec["resource"]["recommended_bed"]

    r = client.post(f"/api/appointments/{appt['id']}/bed-decision", headers=NURSE,
                    json={"bed_needed": True, "bed_code": rec["resource"]["recommended_bed"]}).json()
    assert r["status"] == "ALLOCATED"
    row = next(x for x in client.get("/api/appointments").json() if x["id"] == appt["id"])
    assert row["bed_needed"] is True and row["bed_code"] == r["allocation"]["bed"]
    assert client.post(f"/api/appointments/{appt['id']}/bed-decision", headers=NURSE,
                       json={"bed_needed": False}).status_code == 409

    # "no bed needed" path
    q = _new_patient(client)
    client.patch(f"/api/patients/{q['id']}/vitals", headers=NURSE, json={
        "heart_rate": 80, "spo2": 98, "temperature": 36.8})
    appt2 = _book(client, q["id"], doc, "14:00").json()["appointment"]
    client.patch(f"/api/appointments/{appt2['id']}/visited", headers=NURSE)
    r = client.post(f"/api/appointments/{appt2['id']}/bed-decision", headers=NURSE, json={"bed_needed": False}).json()
    assert r["status"] == "NO_BED_NEEDED"
    row = next(x for x in client.get("/api/appointments").json() if x["id"] == appt2["id"])
    assert row["bed_needed"] is False and row["bed_code"] is None


def test_3_no_diagnosis_for_discharged_patient(client):
    p = _new_patient(client)
    assert client.post("/api/diagnostics", json={"patient_id": p["id"], "test_type": "X-Ray"}).status_code == 200

    with SessionLocal() as db:
        db.query(Patient).filter(Patient.id == p["id"]).update({"status": "DISCHARGED"})
        db.commit()

    r = client.post("/api/diagnostics", json={"patient_id": p["id"], "test_type": "MRI"})
    assert r.status_code == 400 and "discharged" in r.json()["detail"]
    assert client.get(f"/api/resource/patient/{p['id']}").json()["status"] == "ERROR"


def test_5_confidence_drops_when_data_is_missing():
    from app.agents.monitoring_agent import MonitoringAgent
    from app.agents.triage_agent import TriageAgent

    class P:
        id, patient_code, name, age, gender, status = 1, "P900", "X", 30, "Male", "WAITING"
        symptoms = "fever"
        heart_rate, spo2, temperature = 110, 93, 38.6

    agent = TriageAgent()
    agent.client = None  # force the deterministic path
    full = P()
    mon = MonitoringAgent().evaluate_patient(full)
    high = agent.assess_patient(full, mon)

    partial = P()
    partial.spo2 = None
    partial.temperature = None
    low = agent.assess_patient(partial, MonitoringAgent().evaluate_patient(partial))
    assert low.confidence < high.confidence
    assert any("Missing vitals" in f for f in low.confidence_factors)
