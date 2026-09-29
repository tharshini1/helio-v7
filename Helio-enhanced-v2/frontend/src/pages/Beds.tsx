import { useEffect, useState } from "react";
import { BedDouble, Bot, Search } from "lucide-react";

import { API_BASE } from "../config";
import TriageConfidence, { type TriageInfo } from "../components/TriageConfidence";

type Bed = {
  id: number;
  bed_code: string;
  ward_type: string;
  is_occupied: boolean;
  patient_id?: number | null;
  patient_code?: string | null;
};

type Patient = {
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
};

type Recommendation = {
  status?: string;
  patient?: { id: number; code: string; name: string };
  patient_record?: Patient;
  triage?: TriageInfo;
  resource?: {
    patient_id: string;
    category: string;
    priority: string;
    required_ward: string;
    recommended_bed: string | null;
    availability: string;
    available: boolean;
    approval_required: boolean;
    human_intervention_required: boolean;
    reason: string;
  };
};

const show = (v: unknown, unit = "") =>
  v === null || v === undefined || v === "" ? "—" : `${v}${unit}`;

// Group beds by the ward stored in the database.
const wardOf = (bed: Bed) => {
  const w = bed.ward_type.trim().toUpperCase();
  if (w === "ICU") return "ICU";
  if (w === "ER" || w === "EMERGENCY") return "ER";
  return "GENERAL MEDICINE";
};

function Beds() {
  const [beds, setBeds] = useState<Bed[]>([]);
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<Patient[]>([]);
  const [patient, setPatient] = useState<Patient | null>(null);
  const [recommendation, setRecommendation] = useState<Recommendation | null>(null);

  const [loading, setLoading] = useState(false);
  const [allocating, setAllocating] = useState(false);
  const [message, setMessage] = useState("");

  const loadBeds = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/beds`);
      if (!response.ok) throw new Error("Unable to load bed inventory.");
      const data = await response.json();
      setBeds(Array.isArray(data) ? data : []);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to load bed inventory.");
    }
  };

  useEffect(() => {
    loadBeds();
  }, []);

  // Patient search against the real patient dataset
  useEffect(() => {
    if (patient || !query.trim()) {
      setSuggestions([]);
      return;
    }
    const handle = setTimeout(async () => {
      try {
        const res = await fetch(
          `${API_BASE}/api/patients/search?q=${encodeURIComponent(query.trim())}`
        );
        if (res.ok) {
          const rows: Patient[] = await res.json();
          setSuggestions(rows.filter((p) => p.status !== "DISCHARGED"));
        }
      } catch (error) {
        console.error(error);
      }
    }, 250);
    return () => clearTimeout(handle);
  }, [query, patient]);

  const selectPatient = async (selected: Patient) => {
    setPatient(selected);
    setQuery("");
    setSuggestions([]);
    setMessage("");
    setRecommendation(null);
    setLoading(true);

    try {
      const response = await fetch(`${API_BASE}/api/resource/patient/${selected.id}`);
      const data = await response.json();
      if (!response.ok || data.status === "ERROR") {
        throw new Error(data.error || "Bed Agent could not process the request.");
      }
      setRecommendation(data);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to generate recommendation.");
    } finally {
      setLoading(false);
    }
  };

  const clearSelection = () => {
    setPatient(null);
    setRecommendation(null);
    setMessage("");
  };

  const decide = async (approve: boolean) => {
    if (!patient || !recommendation?.resource) return;
    setAllocating(true);
    setMessage("");

    const bed = recommendation.resource.recommended_bed;
    const qs = bed ? `?bed_code=${encodeURIComponent(bed)}` : "";

    try {
      const response = await fetch(
        `${API_BASE}/api/resource/${approve ? "allocate" : "reject"}/${patient.id}${qs}`,
        { method: "POST" }
      );
      const data = await response.json();

      if (approve) {
        if (data.status !== "ALLOCATED") {
          throw new Error(data.message || data.error || "Bed allocation failed.");
        }
        setMessage(`✓ ${data.allocation.bed} allocated to ${data.patient.code}`);
      } else {
        setMessage("Recommendation rejected. No bed was allocated.");
      }

      clearSelectionKeepMessage();
      await loadBeds();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Action failed.");
      await loadBeds();
    } finally {
      setAllocating(false);
    }
  };

  const clearSelectionKeepMessage = () => {
    setPatient(null);
    setRecommendation(null);
  };

  const totalBeds = beds.length;
  const availableBeds = beds.filter((b) => !b.is_occupied).length;
  const icuFree = beds.filter((b) => wardOf(b) === "ICU" && !b.is_occupied).length;

  const renderWard = (title: string, key: string) => {
    const bedsInWard = beds
      .filter((b) => wardOf(b) === key)
      .sort((a, b) => a.bed_code.localeCompare(b.bed_code));
    const free = bedsInWard.filter((b) => !b.is_occupied).length;
    const occupiedPct = bedsInWard.length
      ? Math.round(((bedsInWard.length - free) / bedsInWard.length) * 100)
      : 0;
    const tone = occupiedPct >= 90 ? "high" : occupiedPct >= 70 ? "mid" : "low";

    return (
      <section className="ba-ward">
        <div className="ba-ward-head">
          <div>
            <h3>{title}</h3>
            <span>
              {free} available / {bedsInWard.length} total
            </span>
          </div>
          <span className={`ba-occupancy ${tone}`}>{occupiedPct}% full</span>
        </div>
        <div className="ba-meter" aria-hidden="true">
          <span className={tone} style={{ width: `${occupiedPct}%` }} />
        </div>
        <div className="ba-bed-grid">
          {bedsInWard.map((bed) => (
            <div
              key={bed.bed_code}
              className={`ba-bed ${bed.is_occupied ? "occupied" : "free"}`}
              title={
                bed.is_occupied
                  ? `${bed.bed_code} · occupied${bed.patient_code ? ` by ${bed.patient_code}` : ""}`
                  : `${bed.bed_code} · available`
              }
            >
              <BedDouble size={18} />
              <strong>{bed.bed_code}</strong>
              <small>
                {bed.is_occupied ? bed.patient_code || "Occupied" : "Available"}
              </small>
            </div>
          ))}
        </div>
      </section>
    );
  };

  const r = recommendation?.resource;

  return (
    <div className="page-container bed-page">
      <div className="page-header">
        <div>
          <h1>Bed Management</h1>
          <p>Live bed inventory and human-approved allocation by the Bed Agent.</p>
        </div>
      </div>

      <div className="ba-stats">
        <div className="ba-stat">
          <span>Total Beds</span>
          <strong>{totalBeds}</strong>
        </div>
        <div className="ba-stat ok">
          <span>Available</span>
          <strong>{availableBeds}</strong>
        </div>
        <div className="ba-stat alert">
          <span>Occupied</span>
          <strong>{totalBeds - availableBeds}</strong>
        </div>
        <div className="ba-stat brand">
          <span>ICU Available</span>
          <strong>{icuFree}</strong>
        </div>
      </div>

      <section className="ba-panel">
        <div className="ba-panel-head">
          <div className="ba-panel-icon">
            <Bot size={22} />
          </div>
          <div>
            <h2>Bed Agent</h2>
            <p>
              Select a patient. The agent analyses their record, picks the required
              ward and finds a free bed. Nothing changes until you approve.
            </p>
          </div>
        </div>

        <ol className="ba-steps" aria-label="Bed Agent workflow">
          <li className={patient ? "done" : "active"}>
            <span>1</span> Select patient
          </li>
          <li className={patient ? (loading ? "active" : "done") : ""}>
            <span>2</span> Monitoring &amp; triage
          </li>
          <li className={r ? "active" : ""}>
            <span>3</span> Bed recommendation
          </li>
          <li className={r ? "active" : ""}>
            <span>4</span> Human approval
          </li>
        </ol>

        {!patient && (
          <div className="ba-search">
            <label>
              Search patient by ID or name
              <div className="ba-search-box">
                <Search size={16} />
                <input
                  type="text"
                  placeholder="e.g. P003 or Rahul"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
              </div>
            </label>
            {suggestions.length > 0 && (
              <ul className="ba-suggestions">
                {suggestions.map((s) => (
                  <li key={s.id} onClick={() => selectPatient(s)}>
                    <strong>{s.name}</strong>
                    <span>
                      {s.patient_code} · {s.status}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {patient && (
          <div className="ba-patient">
            <div className="ba-patient-head">
              <div className="ba-avatar">{patient.name.charAt(0).toUpperCase()}</div>
              <div>
                <strong>{patient.name}</strong>
                <span>{patient.patient_code}</span>
              </div>
              <button type="button" className="secondary-button" onClick={clearSelection}>
                Change
              </button>
            </div>
            <div className="ba-vitals">
              <div><span>Age</span><strong>{show(patient.age)}</strong></div>
              <div><span>Gender</span><strong>{show(patient.gender)}</strong></div>
              <div><span>Status</span><strong>{show(patient.status)}</strong></div>
              <div><span>Heart Rate</span><strong>{show(patient.heart_rate)}</strong></div>
              <div><span>SpO₂</span><strong>{show(patient.spo2, "%")}</strong></div>
              <div><span>Temperature</span><strong>{show(patient.temperature, "°C")}</strong></div>
              <div className="wide"><span>Symptoms</span><strong>{show(patient.symptoms)}</strong></div>
            </div>
          </div>
        )}

        {loading && <div className="ba-loading">Bed Agent is analysing the patient…</div>}

        {r && (
          <div className="ba-reco">
            <div className="ba-reco-head">
              <div>
                <span className="ba-eyebrow">BED AGENT RECOMMENDATION</span>
                <h3>{r.recommended_bed || "No bed available"}</h3>
              </div>
              <span className={`ba-priority ${r.priority.toLowerCase()}`}>{r.priority}</span>
            </div>

            <TriageConfidence triage={recommendation?.triage} />

            <div className="ba-reco-grid">
              <div><span>Category</span><strong>{r.category}</strong></div>
              <div><span>Required Ward</span><strong>{r.required_ward}</strong></div>
              <div><span>Availability</span><strong>{r.availability}</strong></div>
              <div><span>Approval</span><strong>{r.approval_required ? "REQUIRED" : "NOT REQUIRED"}</strong></div>
            </div>

            <p className="ba-reason">{r.reason}</p>

            {r.human_intervention_required && (
              <div className="ba-warning">
                Human intervention required — the patient will not be moved to another ward automatically.
              </div>
            )}

            {r.available ? (
              <div className="ba-actions">
                <button className="primary-button" onClick={() => decide(true)} disabled={allocating}>
                  {allocating ? "Working..." : "Approve & Allocate Bed"}
                </button>
                <button className="reject-button" onClick={() => decide(false)} disabled={allocating}>
                  Reject
                </button>
              </div>
            ) : (
              <div className="ba-actions">
                <button className="reject-button" onClick={() => decide(false)} disabled={allocating}>
                  Acknowledge (no allocation)
                </button>
              </div>
            )}
          </div>
        )}

        {message && (
          <div className={`ba-message ${message.startsWith("✓") ? "ok" : ""}`}>{message}</div>
        )}
      </section>

      <div className="ba-legend">
        <span><i className="free" /> Available</span>
        <span><i className="occupied" /> Occupied</span>
      </div>

      <div className="ba-wards">
        {renderWard("ICU", "ICU")}
        {renderWard("Emergency Room", "ER")}
        {renderWard("General Medicine", "GENERAL MEDICINE")}
      </div>
    </div>
  );
}

export default Beds;
