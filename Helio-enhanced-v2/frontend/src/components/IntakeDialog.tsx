import { useState } from "react";

import { API_BASE } from "../config";

export type IntakeTarget = {
  patient_id: number;
  patient_name: string;
  patient_code: string;
  intake_missing: string[];
  patient_age: number | null;
  patient_gender: string | null;
  heart_rate: number | null;
  spo2: number | null;
  temperature: number | null;
  symptoms: string | null;
};

type Props = {
  target: IntakeTarget;
  email: string;
  onClose: () => void;
  onSaved: () => void;
  /** Label of the save button, e.g. "Save & mark visited" or "Save details". */
  submitLabel?: string;
};

const str = (v: number | string | null | undefined) => (v === null || v === undefined ? "" : String(v));

/** Nurse checks and records a new patient's age, gender, heart rate and SpO2. */
export default function IntakeDialog({ target, email, onClose, onSaved, submitLabel = "Save details" }: Props) {
  const [age, setAge] = useState(str(target.patient_age));
  const [gender, setGender] = useState(target.patient_gender ?? "");
  const [heartRate, setHeartRate] = useState(str(target.heart_rate));
  const [spo2, setSpo2] = useState(str(target.spo2));
  const [temperature, setTemperature] = useState(str(target.temperature));
  const [symptoms, setSymptoms] = useState(target.symptoms ?? "");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function save() {
    setError("");
    if (!age || !gender || !heartRate || !spo2 || !temperature) {
      setError("Age, gender, heart rate, SpO₂ and temperature are required.");
      return;
    }
    setSaving(true);
    try {
      const res = await fetch(`${API_BASE}/api/patients/${target.patient_id}/vitals`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", "X-Staff-Email": email },
        body: JSON.stringify({
          age: Number(age),
          gender,
          heart_rate: Number(heartRate),
          spo2: Number(spo2),
          temperature: Number(temperature),
          ...(symptoms.trim() ? { symptoms: symptoms.trim() } : {}),
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Unable to save details.");
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to save details.");
      setSaving(false);
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="appointment-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <span className="eyebrow">NEW PATIENT · NURSE INTAKE</span>
            <h3>{target.patient_name}</h3>
          </div>
          <button className="modal-close" onClick={onClose}>×</button>
        </div>

        <div className="booking-form">
          <p className="intake-note">
            Check and record the patient's details
            {target.intake_missing.length > 0 ? ` (${target.intake_missing.join(", ")} missing)` : ""}.
            They are needed before the patient can be marked as visited.
          </p>

          <div className="form-row">
            <label>
              Age
              <input type="number" min={1} max={120} value={age} onChange={(e) => setAge(e.target.value)} />
            </label>
            <label>
              Gender
              <select value={gender} onChange={(e) => setGender(e.target.value)}>
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
              <input type="number" min={20} max={300} value={heartRate} onChange={(e) => setHeartRate(e.target.value)} />
            </label>
            <label>
              SpO₂ (%)
              <input type="number" min={50} max={100} step="0.1" value={spo2} onChange={(e) => setSpo2(e.target.value)} />
            </label>
            <label>
              Temp (°C)
              <input type="number" min={30} max={45} step="0.1" value={temperature} onChange={(e) => setTemperature(e.target.value)} />
            </label>
          </div>

          <label>
            Symptoms
            <textarea rows={2} value={symptoms} onChange={(e) => setSymptoms(e.target.value)} />
          </label>

          {error && <div className="appointment-message error">{error}</div>}

          <div className="booking-actions">
            <button className="secondary-button" onClick={onClose}>Cancel</button>
            <button className="primary-button" onClick={save} disabled={saving}>
              {saving ? "Saving..." : submitLabel}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
