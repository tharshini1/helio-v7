import { useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Siren, X, CheckCircle2 } from "lucide-react";
import { API_BASE } from "../config";
import type { EmergencyAlertData } from "./EmergencyDoctor";

type EmergencyType = { key: string; label: string; specialty: string };
type RouteDoctor = { id: number; name: string; specialization: string; years_experience: number | null };
type Route = { specialty: string | null; doctors: RouteDoctor[] };

const POLL_MS = 4000;

/**
 * Nurse-side emergency button (topbar) plus its dialog: pick the emergency,
 * see which doctors will be paged, send, then watch for a doctor to respond.
 */
function EmergencyNurse({ email }: { email: string }) {
  const [open, setOpen] = useState(false);
  const [types, setTypes] = useState<EmergencyType[]>([]);
  const [selected, setSelected] = useState("");
  const [route, setRoute] = useState<Route | null>(null);
  const [routeLoading, setRouteLoading] = useState(false);
  const [patient, setPatient] = useState("");
  const [location, setLocation] = useState("Emergency Department");
  const [notes, setNotes] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [alerts, setAlerts] = useState<EmergencyAlertData[]>([]);
  const [trackedId, setTrackedId] = useState<number | null>(null);

  const headers = { "Content-Type": "application/json", "X-Staff-Email": email };

  const loadAlerts = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/api/emergency/alerts?limit=10`);
      if (!response.ok) return;
      const data = await response.json();
      setAlerts(Array.isArray(data) ? data : []);
    } catch {
      /* keep last known state */
    }
  }, []);

  useEffect(() => {
    const first = window.setTimeout(loadAlerts, 0);
    const timer = window.setInterval(loadAlerts, POLL_MS);
    return () => {
      window.clearTimeout(first);
      window.clearInterval(timer);
    };
  }, [loadAlerts]);

  useEffect(() => {
    if (!open || types.length) return;
    fetch(`${API_BASE}/api/emergency/types`)
      .then((r) => (r.ok ? r.json() : []))
      .then((data) => setTypes(Array.isArray(data) ? data : []))
      .catch(() => setError("Could not load emergency types."));
  }, [open, types.length]);

  async function pickType(key: string) {
    setSelected(key);
    setError("");
    setRoute(null);
    setRouteLoading(true);
    try {
      const response = await fetch(
        `${API_BASE}/api/emergency/route?emergency_type=${encodeURIComponent(key)}`,
      );
      if (!response.ok) throw new Error();
      setRoute(await response.json());
    } catch {
      setError("Could not find doctors for this emergency.");
    } finally {
      setRouteLoading(false);
    }
  }

  async function send() {
    if (!selected) {
      setError("Choose the type of emergency first.");
      return;
    }
    setSending(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE}/api/emergency/alerts`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          emergency_type: selected,
          patient_label: patient,
          location,
          notes,
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(
          typeof data.detail === "string" ? data.detail : "Could not send the alert.",
        );
      }
      setTrackedId(data.id);
      await loadAlerts();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not send the alert.");
    } finally {
      setSending(false);
    }
  }

  async function cancelAlert(id: number) {
    setError("");
    try {
      const response = await fetch(`${API_BASE}/api/emergency/alerts/${id}/cancel`, {
        method: "PATCH",
        headers,
      });
      if (!response.ok) throw new Error();
      await loadAlerts();
    } catch {
      setError("Could not cancel the alert.");
    }
  }

  function startNew() {
    setTrackedId(null);
    setSelected("");
    setRoute(null);
    setPatient("");
    setNotes("");
    setError("");
  }

  const activeAlerts = alerts.filter((a) => a.status === "ACTIVE");
  const tracked =
    (trackedId !== null ? alerts.find((a) => a.id === trackedId) : undefined) ??
    undefined;

  return (
    <>
      <button
        type="button"
        className={`em-trigger ${activeAlerts.length ? "em-trigger-live" : ""}`}
        onClick={() => setOpen(true)}
        aria-label="Raise emergency alert" title="Emergency alert"
      >
        <Siren size={17} />
        <span>{activeAlerts.length ? `Emergency · ${activeAlerts.length} active` : "Emergency"}</span>
      </button>

      {open && createPortal(
        <div className="em-modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && setOpen(false)}>
          <div className="em-modal" role="dialog" aria-modal="true" aria-labelledby="em-modal-title">
            <div className="em-modal-head">
              <div>
                <h3 id="em-modal-title">
                  <Siren size={20} /> Emergency alert
                </h3>
                <p>For a major accident or a very critical patient. This sounds a siren for the matching doctors.</p>
              </div>
              <button type="button" className="em-close" onClick={() => setOpen(false)} aria-label="Close">
                <X size={18} />
              </button>
            </div>

            {tracked ? (
              <div className="em-status">
                <div className={`em-status-banner em-status-${tracked.status.toLowerCase()}`}>
                  {tracked.status === "ACTIVE" && (
                    <>
                      <span className="em-live-dot" />
                      <div>
                        <strong>Siren is sounding. Waiting for a doctor to respond...</strong>
                        <small>{tracked.emergency_label} · {tracked.patient_label}</small>
                      </div>
                    </>
                  )}
                  {tracked.status === "ACKNOWLEDGED" && (
                    <>
                      <CheckCircle2 size={22} />
                      <div>
                        <strong>{tracked.acknowledged_by} is responding</strong>
                        <small>{tracked.emergency_label} · {tracked.patient_label}</small>
                      </div>
                    </>
                  )}
                  {tracked.status === "CANCELLED" && (
                    <div>
                      <strong>Alert cancelled</strong>
                      <small>{tracked.emergency_label} · {tracked.patient_label}</small>
                    </div>
                  )}
                </div>

                <p className="em-label">Doctors paged ({tracked.required_specialty})</p>
                <ul className="em-doctor-list">
                  {tracked.paged_doctors.map((d) => (
                    <li key={d.id}>
                      <strong>{d.name}</strong>
                      <span>{d.specialization}</span>
                    </li>
                  ))}
                </ul>

                {error && <p className="em-error" role="alert">{error}</p>}

                <div className="em-actions">
                  {tracked.status === "ACTIVE" && (
                    <button type="button" className="em-secondary" onClick={() => cancelAlert(tracked.id)}>
                      Cancel (false alarm)
                    </button>
                  )}
                  <button type="button" className="em-secondary" onClick={startNew}>
                    New alert
                  </button>
                </div>
              </div>
            ) : (
              <div className="em-form">
                <p className="em-label">What is the emergency?</p>
                <div className="em-type-grid">
                  {types.map((t) => (
                    <button
                      type="button"
                      key={t.key}
                      className={`em-type ${selected === t.key ? "selected" : ""}`}
                      onClick={() => pickType(t.key)}
                    >
                      {t.label}
                    </button>
                  ))}
                </div>

                {selected && (
                  <div className="em-route">
                    {routeLoading ? (
                      <span>Finding the right doctors...</span>
                    ) : route && route.doctors.length > 0 ? (
                      <>
                        <strong>Will page {route.specialty}:</strong>{" "}
                        {route.doctors.map((d) => d.name).join(", ")}
                      </>
                    ) : (
                      <span className="em-route-warn">
                        No {route?.specialty ?? "matching"} doctor is available right now. Call the emergency desk directly.
                      </span>
                    )}
                  </div>
                )}

                <label className="em-field">
                  <span>Patient (optional)</span>
                  <input
                    type="text"
                    placeholder="e.g. Male, about 40, bike collision"
                    value={patient}
                    maxLength={150}
                    onChange={(e) => setPatient(e.target.value)}
                  />
                </label>
                <label className="em-field">
                  <span>Where is the patient?</span>
                  <input
                    type="text"
                    value={location}
                    maxLength={120}
                    onChange={(e) => setLocation(e.target.value)}
                  />
                </label>
                <label className="em-field">
                  <span>Notes for the doctor (optional)</span>
                  <textarea
                    rows={2}
                    placeholder="Airway compromised, heavy bleeding, ETA 3 min..."
                    value={notes}
                    maxLength={1000}
                    onChange={(e) => setNotes(e.target.value)}
                  />
                </label>

                {error && <p className="em-error" role="alert">{error}</p>}

                <button
                  type="button"
                  className="em-send"
                  disabled={sending || !selected || (route !== null && route.doctors.length === 0)}
                  onClick={send}
                >
                  <Siren size={18} />
                  {sending ? "Sending..." : "Sound the alarm"}
                </button>
              </div>
            )}
          </div>
        </div>,
        document.body,
      )}
    </>
  );
}

export default EmergencyNurse;
