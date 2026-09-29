import { useEffect, useState } from "react";

import { API_BASE } from "../config";
import BedDecisionDialog from "../components/BedDecisionDialog";
import IntakeDialog, { type IntakeTarget } from "../components/IntakeDialog";

interface Patient {
  id: number;
  patient_code: string;
  name: string;
  age: number;
  gender: string;
  symptoms: string | null;
  heart_rate: number | null;
  spo2: number | null;
  temperature: number | null;
  status: string;
  intake_missing?: string[];
}

interface DoctorInfo {
  id: number;
  name: string;
  specialization: string;
  years_experience: number | null;
  is_available: boolean;
}

interface Recommendation {
  specialization: string | null;
  recommended_doctor: DoctorInfo | null;
  alternatives: DoctorInfo[];
  available: boolean;
  reason: string;
}

interface Slot {
  time: string;
  available: boolean;
  state: "AVAILABLE" | "BOOKED" | "PAST";
}

interface SlotInfo {
  booked: string[];
  slots: Slot[];
}

interface Appointment {
  id: number;
  patient_id: number;
  patient_code: string;
  patient_name: string;
  doctor_name: string;
  specialization: string;
  appointment_date: string;
  appointment_time: string;
  reason: string;
  status: string;
  visited_at?: string | null;
  visited_by?: string | null;
  bed_needed?: boolean | null;
  bed_code?: string | null;
  patient_status: string;
  intake_missing: string[];
  patient_age: number | null;
  patient_gender: string | null;
  heart_rate: number | null;
  spo2: number | null;
  temperature: number | null;
  symptoms: string | null;
}

const pad = (n: number) => String(n).padStart(2, "0");
const todayString = () => {
  const d = new Date();
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
};
const nowTimeString = () => {
  const d = new Date();
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
};
const show = (value: unknown, unit = "") =>
  value === null || value === undefined || value === "" ? "—" : `${value}${unit}`;

const emptyNew = {
  name: "",
  age: "",
  gender: "Male",
  symptoms: "",
  heart_rate: "",
  spo2: "",
  temperature: "",
};
const emptyVitals = { heart_rate: "", spo2: "", temperature: "", symptoms: "", age: "", gender: "" };

const intakeTargetFromPatient = (p: Patient): IntakeTarget => ({
  patient_id: p.id,
  patient_name: p.name,
  patient_code: p.patient_code,
  intake_missing: p.intake_missing ?? [],
  patient_age: p.age || null,
  patient_gender: p.gender && p.gender !== "Not specified" ? p.gender : null,
  heart_rate: p.heart_rate,
  spo2: p.spo2,
  temperature: p.temperature,
  symptoms: p.symptoms,
});

const intakeTargetFromAppointment = (a: Appointment): IntakeTarget => ({
  patient_id: a.patient_id,
  patient_name: a.patient_name,
  patient_code: a.patient_code,
  intake_missing: a.intake_missing,
  patient_age: a.patient_age,
  patient_gender: a.patient_gender,
  heart_rate: a.heart_rate,
  spo2: a.spo2,
  temperature: a.temperature,
  symptoms: a.symptoms,
});

type AppointmentsProps = {
  role?: string;
  email?: string;
};

function Appointments({ role, email = "" }: AppointmentsProps) {
  const isNurse = role === "Nurse";
  const [editingVitals, setEditingVitals] = useState(false);
  const [vitals, setVitals] = useState(emptyVitals);
  const [visitingId, setVisitingId] = useState<number | null>(null);
  const [intakeFor, setIntakeFor] = useState<Appointment | null>(null);
  const [bedFor, setBedFor] = useState<Appointment | null>(null);
  const [slotState, setSlotState] = useState<{ key: string; data: SlotInfo } | null>(null);
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [patientList, setPatientList] = useState<Patient[]>([]);
  const [intakeTarget, setIntakeTarget] = useState<IntakeTarget | null>(null);
  const [availableDoctors, setAvailableDoctors] = useState(0);

  const [showForm, setShowForm] = useState(false);
  const [loading, setLoading] = useState(true);
  const [booking, setBooking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [formError, setFormError] = useState("");

  const [mode, setMode] = useState<"existing" | "new">("existing");
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<Patient[]>([]);
  const [patient, setPatient] = useState<Patient | null>(null);
  const [newPatient, setNewPatient] = useState(emptyNew);

  const [recommendation, setRecommendation] = useState<Recommendation | null>(null);
  const [doctorId, setDoctorId] = useState("");
  const [date, setDate] = useState("");
  const [time, setTime] = useState("");
  const [reason, setReason] = useState("");

  useEffect(() => {
    loadData();
  }, []);

  // Debounced patient search (patient code or name)
  useEffect(() => {
    if (mode !== "existing" || patient || !query.trim()) {
      setSuggestions([]);
      return;
    }
    const handle = setTimeout(async () => {
      try {
        const res = await fetch(
          `${API_BASE}/api/patients/search?q=${encodeURIComponent(query.trim())}`
        );
        if (res.ok) setSuggestions(await res.json());
      } catch (error) {
        console.error(error);
      }
    }, 250);
    return () => clearTimeout(handle);
  }, [query, mode, patient]);

  // Which slots the chosen doctor has free on the chosen date
  const slotKey = doctorId && date ? `${doctorId}|${date}` : "";
  useEffect(() => {
    if (!slotKey) return;
    let cancelled = false;
    fetch(`${API_BASE}/api/appointments/slots?doctor_id=${doctorId}&date=${date}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (!cancelled && data) setSlotState({ key: slotKey, data });
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [slotKey, doctorId, date, appointments]);
  // Ignore slots fetched for a previous doctor/date.
  const slotInfo = slotState && slotState.key === slotKey ? slotState.data : null;

  async function loadData() {
    try {
      const [a, p, d] = await Promise.all([
        fetch(`${API_BASE}/api/appointments`),
        fetch(`${API_BASE}/api/patients`),
        fetch(`${API_BASE}/api/doctors`),
      ]);
      if (!a.ok || !p.ok || !d.ok) throw new Error("Failed to load appointment data.");
      setAppointments(await a.json());
      const allPatients: Patient[] = await p.json();
      setPatientList(Array.isArray(allPatients) ? allPatients : []);
      const doctors: DoctorInfo[] = await d.json();
      setAvailableDoctors(doctors.filter((x) => x.is_available).length);
    } catch (error) {
      console.error(error);
      setMessage("Unable to load appointment data.");
    } finally {
      setLoading(false);
    }
  }

  function resetForm() {
    setMode("existing");
    setQuery("");
    setSuggestions([]);
    setPatient(null);
    setEditingVitals(false);
    setNewPatient(emptyNew);
    setRecommendation(null);
    setDoctorId("");
    setDate("");
    setTime("");
    setReason("");
    setFormError("");
  }

  async function analysePatient(selected: Patient) {
    setPatient(selected);
    setSuggestions([]);
    setQuery("");
    setReason(selected.symptoms && selected.symptoms !== "No symptoms" ? selected.symptoms : "");
    setBusy(true);
    setFormError("");
    try {
      const res = await fetch(`${API_BASE}/api/appointments/recommend/${selected.id}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Could not get a recommendation.");
      setRecommendation(data);
      setDoctorId(data.recommended_doctor ? String(data.recommended_doctor.id) : "");
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "Recommendation failed.");
    } finally {
      setBusy(false);
    }
  }

  async function registerNewPatient() {
    setFormError("");
    if (!newPatient.name.trim() || !newPatient.age || !newPatient.gender || !newPatient.symptoms.trim()) {
      setFormError("Name, age, gender and symptoms are required.");
      return;
    }
    if (isNurse && (!newPatient.heart_rate || !newPatient.spo2 || !newPatient.temperature)) {
      setFormError("Heart rate, SpO₂ and temperature are required.");
      return;
    }
    setBusy(true);
    try {
      const res = await fetch(`${API_BASE}/api/patients/new`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Staff-Email": email },
        body: JSON.stringify({
          name: newPatient.name.trim(),
          age: Number(newPatient.age),
          gender: newPatient.gender,
          symptoms: newPatient.symptoms.trim(),
          ...(isNurse
            ? {
                heart_rate: Number(newPatient.heart_rate),
                spo2: Number(newPatient.spo2),
                temperature: Number(newPatient.temperature),
              }
            : {}),
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to create patient.");
      setBusy(false);
      await analysePatient(data);
      loadData();
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "Failed to create patient.");
      setBusy(false);
    }
  }

  function startEditVitals() {
    if (!patient) return;
    setVitals({
      age: patient.age ? String(patient.age) : "",
      gender: patient.gender && patient.gender !== "Not specified" ? patient.gender : "",
      heart_rate: patient.heart_rate != null ? String(patient.heart_rate) : "",
      spo2: patient.spo2 != null ? String(patient.spo2) : "",
      temperature: patient.temperature != null ? String(patient.temperature) : "",
      symptoms: patient.symptoms ?? "",
    });
    setFormError("");
    setEditingVitals(true);
  }

  async function saveVitals() {
    if (!patient) return;
    if (!vitals.age || !vitals.gender || !vitals.heart_rate || !vitals.spo2 || !vitals.temperature || !vitals.symptoms.trim()) {
      setFormError("Age, gender, heart rate, SpO₂, temperature and symptoms are required.");
      return;
    }
    setBusy(true);
    setFormError("");
    try {
      const res = await fetch(`${API_BASE}/api/patients/${patient.id}/vitals`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", "X-Staff-Email": email },
        body: JSON.stringify({
          age: Number(vitals.age),
          gender: vitals.gender,
          heart_rate: Number(vitals.heart_rate),
          spo2: Number(vitals.spo2),
          temperature: Number(vitals.temperature),
          symptoms: vitals.symptoms.trim(),
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Unable to save vitals.");
      setPatient(data);
      setEditingVitals(false);
      setMessage("Vitals and symptoms saved.");
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "Unable to save vitals.");
    } finally {
      setBusy(false);
    }
  }

  async function bookAppointment() {
    setFormError("");
    if (!patient || !doctorId || !date || !time || !reason.trim()) {
      setFormError("Please complete patient, doctor, date, time and reason.");
      return;
    }
    if (slotInfo?.booked.includes(time)) {
      setFormError("Slot not available — choose another time.");
      return;
    }
    // Frontend guard only — the backend validates independently.
    if (date < todayString() || (date === todayString() && time <= nowTimeString())) {
      setFormError("Please choose a future date and time.");
      return;
    }

    setBooking(true);
    try {
      const res = await fetch(`${API_BASE}/api/appointments`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          patient_id: patient.id,
          doctor_id: Number(doctorId),
          appointment_date: date,
          appointment_time: time,
          reason: reason.trim(),
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Booking failed.");

      setMessage("Appointment booked successfully.");
      setShowForm(false);
      resetForm();
      await loadData();
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "Unable to book appointment.");
    } finally {
      setBooking(false);
    }
  }

  async function cancelAppointment(id: number) {
    if (!window.confirm("Cancel this appointment?")) return;
    try {
      const res = await fetch(`${API_BASE}/api/appointments/${id}/cancel`, { method: "PATCH" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Cancellation failed.");
      setMessage("Appointment cancelled.");
      await loadData();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to cancel appointment.");
    }
  }

  function startVisit(a: Appointment) {
    // A new patient's details must be checked and recorded by the nurse first.
    if (a.intake_missing.length > 0) setIntakeFor(a);
    else markVisited(a);
  }

  async function markVisited(a: Appointment) {
    const id = a.id;
    setVisitingId(id);
    setMessage("");
    try {
      const res = await fetch(`${API_BASE}/api/appointments/${id}/visited`, {
        method: "PATCH",
        headers: { "X-Staff-Email": email },
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Unable to mark as visited.");
      setMessage("Patient marked as visited.");
      setBedFor(a); // next: is a bed needed?
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to mark as visited.");
    } finally {
      setVisitingId(null);
      // Reload either way: a slot that just expired shows up as not visited.
      await loadData();
    }
  }

  const patientCount = patientList.length;
  const awaitingIntake = patientList.filter((p) => p.status === "NEW" && (p.intake_missing?.length ?? 0) > 0);
  const count = (status: string) => appointments.filter((a) => a.status === status).length;
  const recommended = recommendation?.recommended_doctor;
  const doctorChoices = recommended ? [recommended, ...(recommendation?.alternatives ?? [])] : [];

  if (loading) return <div className="loading-state">Loading appointments...</div>;

  return (
    <div className="appointments-page">
      <div className="module-heading">
        <div>
          <span className="eyebrow">PATIENT SCHEDULING</span>
          <h3>Appointments</h3>
          <p>The Appointment Agent recommends an available doctor from the patient's record.</p>
        </div>
        <button
          className="primary-button"
          onClick={() => {
            setMessage("");
            resetForm();
            setShowForm(true);
          }}
        >
          + Book Appointment
        </button>
      </div>

      {message && <div className="appointment-message">{message}</div>}

      <div className="appointment-summary">
        <div className="summary-card"><span>Scheduled</span><strong>{count("SCHEDULED")}</strong></div>
        <div className="summary-card"><span>Visited</span><strong>{count("VISITED")}</strong></div>
        <div className="summary-card"><span>Not Visited</span><strong>{count("NOT_VISITED")}</strong></div>
        <div className="summary-card"><span>Cancelled</span><strong>{count("CANCELLED") + count("AUTO_CANCELLED")}</strong></div>
        <div className="summary-card"><span>Available Doctors</span><strong>{availableDoctors}</strong></div>
        <div className="summary-card"><span>Registered Patients</span><strong>{patientCount}</strong></div>
      </div>

      {awaitingIntake.length > 0 && (
        <section className="module-card intake-panel">
          <div className="module-card-header">
            <div>
              <h4>New patients awaiting nurse intake</h4>
              <span>
                {isNurse
                  ? "Check and add age, gender, heart rate and SpO₂."
                  : "A nurse must check and add these details."}
              </span>
            </div>
          </div>
          <ul className="intake-list">
            {awaitingIntake.map((p) => (
              <li key={p.id}>
                <div>
                  <strong>{p.name}</strong>
                  <span className="table-secondary">
                    {p.patient_code} · missing: {p.intake_missing?.join(", ")}
                  </span>
                </div>
                {isNurse && (
                  <button className="bed-button" onClick={() => setIntakeTarget(intakeTargetFromPatient(p))}>
                    Add details
                  </button>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="module-card">
        <div className="module-card-header">
          <div>
            <h4>Appointment Schedule</h4>
            <span>Live data from Helio backend</span>
          </div>
        </div>

        {appointments.length === 0 ? (
          <div className="empty-module">
            <div className="empty-module-icon">▣</div>
            <strong>No appointments yet</strong>
            <span>Book the first appointment to begin the workflow.</span>
          </div>
        ) : (
          <div className="appointment-table-wrapper">
            <table className="appointment-table">
              <thead>
                <tr>
                  <th>Patient</th><th>Doctor</th><th>Date</th><th>Time</th>
                  <th>Reason</th><th>Status</th><th></th>
                </tr>
              </thead>
              <tbody>
                {appointments.map((a) => (
                  <tr key={a.id}>
                    <td>
                      <div className="table-person">
                        <div className="table-avatar">{a.patient_name.charAt(0)}</div>
                        <div>
                          <strong>{a.patient_name}</strong>
                          <span>{a.patient_code}</span>
                        </div>
                      </div>
                    </td>
                    <td>
                      <strong>{a.doctor_name}</strong>
                      <span className="table-secondary">{a.specialization}</span>
                    </td>
                    <td>{a.appointment_date}</td>
                    <td><strong>{a.appointment_time}</strong></td>
                    <td className="reason-cell">{a.reason}</td>
                    <td>
                      <span className={`appointment-status ${a.status.toLowerCase()}`}>
                        {a.status.replaceAll("_", " ")}
                      </span>
                      {a.status === "VISITED" && a.visited_at && (
                        <span className="table-secondary">
                          {new Date(a.visited_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                          {a.visited_by ? ` · ${a.visited_by}` : ""}
                        </span>
                      )}
                      {a.status === "SCHEDULED" && a.intake_missing.length > 0 && (
                        <span className="appointment-badge warn">Nurse intake pending</span>
                      )}
                      {a.status === "VISITED" && a.bed_code && (
                        <span className="appointment-badge ok">Bed {a.bed_code}</span>
                      )}
                      {a.status === "VISITED" && a.bed_needed === true && !a.bed_code && (
                        <span className="appointment-badge warn">Bed needed · none allocated</span>
                      )}
                      {a.status === "VISITED" && a.bed_needed === false && (
                        <span className="appointment-badge">No bed needed</span>
                      )}
                      {a.status === "VISITED" && a.bed_needed == null && (
                        <span className="appointment-badge warn">Bed decision pending</span>
                      )}
                    </td>
                    <td>
                      {a.status === "VISITED" && isNurse && a.bed_needed !== false && !a.bed_code && (
                        <div className="appointment-actions">
                          <button className="bed-button" onClick={() => setBedFor(a)}>
                            Bed decision
                          </button>
                        </div>
                      )}
                      {a.status === "SCHEDULED" && (
                        <div className="appointment-actions">
                          {isNurse && a.intake_missing.length > 0 && (
                            <button className="bed-button" onClick={() => setIntakeTarget(intakeTargetFromAppointment(a))}>
                              Add details
                            </button>
                          )}
                          {isNurse && (
                            <button
                              className="visited-button"
                              onClick={() => startVisit(a)}
                              disabled={visitingId === a.id}
                            >
                              {visitingId === a.id ? "Saving..." : "Visited"}
                            </button>
                          )}
                          <button className="cancel-button" onClick={() => cancelAppointment(a.id)}>
                            Cancel
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {showForm && (
        <div className="modal-overlay" onClick={() => setShowForm(false)}>
          <div className="appointment-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div>
                <span className="eyebrow">NEW APPOINTMENT</span>
                <h3>Book Appointment</h3>
              </div>
              <button className="modal-close" onClick={() => setShowForm(false)}>×</button>
            </div>

            <div>
              {/* MODE */}
              <div className="mode-toggle">
                <button
                  type="button"
                  className={mode === "existing" ? "active" : ""}
                  onClick={() => { resetForm(); setMode("existing"); }}
                >
                  Existing Patient
                </button>
                <button
                  type="button"
                  className={mode === "new" ? "active" : ""}
                  onClick={() => { resetForm(); setMode("new"); }}
                >
                  New Patient
                </button>
              </div>

              {/* EXISTING: SEARCH */}
              {mode === "existing" && !patient && (
                <div className="patient-search">
                  <label>
                    Search by Patient ID or name
                    <input
                      type="text"
                      placeholder="e.g. P003 or Rahul"
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                      autoFocus
                    />
                  </label>
                  {suggestions.length > 0 && (
                    <ul className="patient-suggestions">
                      {suggestions.map((s) => (
                        <li key={s.id} onClick={() => analysePatient(s)}>
                          {s.name} — {s.patient_code}
                        </li>
                      ))}
                    </ul>
                  )}
                  {query.trim() && suggestions.length === 0 && (
                    <span className="table-secondary">No matching patient yet…</span>
                  )}
                </div>
              )}

              {/* NEW PATIENT: name, age, gender, symptoms (+ vitals when a nurse is signed in) */}
              {mode === "new" && !patient && (
                <div className="new-patient-form">
                  <h4>New Patient Details</h4>
                  <div className="form-row">
                    <label>
                      Name
                      <input
                        type="text"
                        value={newPatient.name}
                        onChange={(e) => setNewPatient({ ...newPatient, name: e.target.value })}
                      />
                    </label>
                    <label>
                      Age
                      <input
                        type="number"
                        min={0}
                        max={120}
                        value={newPatient.age}
                        onChange={(e) => setNewPatient({ ...newPatient, age: e.target.value })}
                      />
                    </label>
                  </div>
                  <label>
                    Gender
                    <select
                      value={newPatient.gender}
                      onChange={(e) => setNewPatient({ ...newPatient, gender: e.target.value })}
                    >
                      <option>Male</option>
                      <option>Female</option>
                      <option>Other</option>
                    </select>
                  </label>
                  {isNurse && (
                    <div className="form-row">
                      <label>
                        Heart rate (bpm)
                        <input
                          type="number"
                          min={20}
                          max={300}
                          value={newPatient.heart_rate}
                          onChange={(e) => setNewPatient({ ...newPatient, heart_rate: e.target.value })}
                        />
                      </label>
                      <label>
                        SpO₂ (%)
                        <input
                          type="number"
                          min={50}
                          max={100}
                          step="0.1"
                          value={newPatient.spo2}
                          onChange={(e) => setNewPatient({ ...newPatient, spo2: e.target.value })}
                        />
                      </label>
                      <label>
                        Temperature (°C)
                        <input
                          type="number"
                          min={30}
                          max={45}
                          step="0.1"
                          value={newPatient.temperature}
                          onChange={(e) => setNewPatient({ ...newPatient, temperature: e.target.value })}
                        />
                      </label>
                    </div>
                  )}
                  {!isNurse && (
                    <div className="intake-note">
                      Heart rate, SpO₂ and temperature are added by a nurse — sign in as a nurse
                      (or use “Add details” on the Appointments page) to record them.
                    </div>
                  )}
                  <label>
                    Medical Condition / Symptoms
                    <textarea
                      rows={2}
                      placeholder="Example: Fever and sore throat"
                      value={newPatient.symptoms}
                      onChange={(e) => setNewPatient({ ...newPatient, symptoms: e.target.value })}
                    />
                  </label>
                  <button
                    type="button"
                    className="primary-button"
                    onClick={registerNewPatient}
                    disabled={busy}
                  >
                    {busy ? "Registering..." : "Register & Find Doctor"}
                  </button>
                </div>
              )}

              {/* SELECTED PATIENT RECORD */}
              {patient && (
                <div className="selected-patient-card">
                  <div className="selected-patient-head">
                    <strong>{patient.patient_code} — {patient.name}</strong>
                    <div className="form-actions-inline">
                      {isNurse && !editingVitals && (
                        <button type="button" className="secondary-button" onClick={startEditVitals}>
                          {patient.heart_rate == null || !patient.age || !patient.gender ? "Add patient details" : "Update details"}
                        </button>
                      )}
                      <button type="button" className="secondary-button" onClick={resetForm}>
                        Change
                      </button>
                    </div>
                  </div>
                  {isNurse && editingVitals && (
                    <div className="new-patient-form">
                      <div className="form-row">
                        <label>
                          Age
                          <input type="number" min={1} max={120} value={vitals.age}
                            onChange={(e) => setVitals({ ...vitals, age: e.target.value })} />
                        </label>
                        <label>
                          Gender
                          <select value={vitals.gender} onChange={(e) => setVitals({ ...vitals, gender: e.target.value })}>
                            <option value="">Select</option>
                            <option>Male</option>
                            <option>Female</option>
                            <option>Other</option>
                          </select>
                        </label>
                      </div>
                      <div className="form-row">
                        <label>
                          Heart rate (bpm)
                          <input type="number" min={20} max={300} value={vitals.heart_rate}
                            onChange={(e) => setVitals({ ...vitals, heart_rate: e.target.value })} />
                        </label>
                        <label>
                          SpO₂ (%)
                          <input type="number" min={50} max={100} step="0.1" value={vitals.spo2}
                            onChange={(e) => setVitals({ ...vitals, spo2: e.target.value })} />
                        </label>
                        <label>
                          Temperature (°C)
                          <input type="number" min={30} max={45} step="0.1" value={vitals.temperature}
                            onChange={(e) => setVitals({ ...vitals, temperature: e.target.value })} />
                        </label>
                      </div>
                      <label>
                        Symptoms
                        <textarea rows={2} value={vitals.symptoms}
                          onChange={(e) => setVitals({ ...vitals, symptoms: e.target.value })} />
                      </label>
                      <div className="form-actions-inline">
                        <button type="button" className="primary-button" onClick={saveVitals} disabled={busy}>
                          {busy ? "Saving..." : "Save details"}
                        </button>
                        <button type="button" className="secondary-button" onClick={() => setEditingVitals(false)}>
                          Cancel
                        </button>
                      </div>
                    </div>
                  )}
                  <div className="patient-record-grid">
                    <div><span>Age</span><strong>{show(patient.age)}</strong></div>
                    <div><span>Gender</span><strong>{show(patient.gender)}</strong></div>
                    <div><span>Heart Rate</span><strong>{show(patient.heart_rate)}</strong></div>
                    <div><span>SpO₂</span><strong>{show(patient.spo2, "%")}</strong></div>
                    <div><span>Temperature</span><strong>{show(patient.temperature, "°C")}</strong></div>
                    <div className="wide"><span>Symptoms</span><strong>{show(patient.symptoms)}</strong></div>
                  </div>
                </div>
              )}

              {busy && patient && <div className="table-secondary">Appointment Agent is analysing…</div>}

              {/* RECOMMENDATION */}
              {patient && recommendation && (
                <div className="doctor-recommendation">
                  <span className="agent-label">APPOINTMENT AGENT RECOMMENDATION</span>
                  {recommended ? (
                    <>
                      <h4>{recommended.name}</h4>
                      <p>
                        {recommendation.specialization} · Currently available
                        {recommended.years_experience
                          ? ` · ${recommended.years_experience} yrs experience`
                          : ""}
                      </p>
                    </>
                  ) : (
                    <h4>No suitable doctor currently available</h4>
                  )}
                  <p className="recommendation-reason">{recommendation.reason}</p>

                  {doctorChoices.length > 1 && (
                    <label>
                      Doctor
                      <select value={doctorId} onChange={(e) => setDoctorId(e.target.value)}>
                        {doctorChoices.map((d, i) => (
                          <option key={d.id} value={d.id}>
                            {d.name} — {d.specialization}
                            {i === 0 ? " (recommended)" : ""}
                          </option>
                        ))}
                      </select>
                    </label>
                  )}
                </div>
              )}

              {/* SCHEDULE */}
              {patient && recommended && (
                <>
                  <div className="form-row">
                    <label>
                      Date
                      <input
                        type="date"
                        min={todayString()}
                        value={date}
                        onChange={(e) => setDate(e.target.value)}
                      />
                    </label>
                    <label>
                      Time
                      <input
                        type="time"
                        min={date === todayString() ? nowTimeString() : undefined}
                        value={time}
                        onChange={(e) => setTime(e.target.value)}
                      />
                    </label>
                  </div>

                  {slotInfo && (
                    <div className="slot-picker">
                      <span>Doctor's slots on {date} (struck-through = not available)</span>
                      <div className="slot-grid">
                        {slotInfo.slots.map((slot) => (
                          <button
                            type="button"
                            key={slot.time}
                            className={`slot-chip ${slot.state === "BOOKED" ? "booked" : ""} ${time === slot.time ? "selected" : ""}`}
                            disabled={!slot.available}
                            title={slot.state === "BOOKED" ? "Slot not available — already booked" : slot.state === "PAST" ? "Time has passed" : "Select this slot"}
                            onClick={() => setTime(slot.time)}
                          >
                            {slot.time}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  {slotInfo?.booked.includes(time) && (
                    <div className="slot-unavailable">
                      Slot not available — this doctor is already booked at {time} on {date}. Please pick another time.
                    </div>
                  )}

                  <label>
                    Reason for Visit
                    <textarea
                      rows={3}
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                      placeholder="Example: Follow-up consultation"
                    />
                  </label>
                </>
              )}

              {formError && <div className="appointment-message error">{formError}</div>}

              <div className="booking-actions">
                <button className="secondary-button" onClick={() => setShowForm(false)}>
                  Cancel
                </button>
                <button
                  className="primary-button"
                  onClick={bookAppointment}
                  disabled={booking || !patient || !recommended || !!slotInfo?.booked.includes(time)}
                >
                  {booking ? "Booking..." : "Book Appointment"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {intakeFor && (
        <IntakeDialog
          target={intakeFor}
          email={email}
          submitLabel="Save & mark visited"
          onClose={() => setIntakeFor(null)}
          onSaved={() => {
            const a = intakeFor;
            setIntakeFor(null);
            markVisited(a);
          }}
        />
      )}

      {intakeTarget && (
        <IntakeDialog
          target={intakeTarget}
          email={email}
          submitLabel="Save details"
          onClose={() => setIntakeTarget(null)}
          onSaved={() => {
            setIntakeTarget(null);
            setMessage("Patient details saved.");
            loadData();
          }}
        />
      )}

      {bedFor && (
        <BedDecisionDialog
          appointmentId={bedFor.id}
          patientName={bedFor.patient_name}
          email={email}
          onClose={() => setBedFor(null)}
          onDone={(msg) => {
            setBedFor(null);
            setMessage(msg);
            loadData();
          }}
        />
      )}
    </div>
  );
}

export default Appointments;
