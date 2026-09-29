import { useCallback, useEffect, useState } from "react";
import { Siren, VolumeX } from "lucide-react";
import { API_BASE } from "../config";
import { useSiren } from "./useSiren";

export type EmergencyAlertData = {
  id: number;
  emergency_label: string;
  required_specialty: string;
  patient_label: string;
  location: string | null;
  notes: string | null;
  paged_doctors: { id: number; name: string; specialization: string }[];
  status: "ACTIVE" | "ACKNOWLEDGED" | "CANCELLED";
  raised_by: string;
  created_at: string | null;
  acknowledged_by: string | null;
};

const POLL_MS = 3000;

/**
 * Full-screen emergency alert for a signed-in doctor. Polls for active alerts
 * that page this doctor, sounds the siren until they respond.
 */
function EmergencyDoctor({ email }: { email: string }) {
  const [alerts, setAlerts] = useState<EmergencyAlertData[]>([]);
  const [mutedFor, setMutedFor] = useState<number | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/api/emergency/alerts/mine`, {
        headers: { "X-Staff-Email": email },
      });
      if (!response.ok) return;
      const data = await response.json();
      setAlerts(Array.isArray(data) ? data : []);
    } catch {
      /* server briefly unreachable: keep the last known state */
    }
  }, [email]);

  useEffect(() => {
    const first = window.setTimeout(load, 0);
    const timer = window.setInterval(load, POLL_MS);
    return () => {
      window.clearTimeout(first);
      window.clearInterval(timer);
    };
  }, [load]);

  const newest = alerts[0];
  const active = alerts.length > 0;
  // Muting silences the current alert only; a new alert sounds again.
  const muted = newest !== undefined && mutedFor === newest.id;
  const { blocked } = useSiren(active, muted);

  useEffect(() => {
    if (!active) return;
    const original = document.title;
    let on = true;
    const timer = window.setInterval(() => {
      document.title = on ? "🚨 EMERGENCY ALERT" : original;
      on = !on;
    }, 800);
    return () => {
      window.clearInterval(timer);
      document.title = original;
    };
  }, [active]);

  async function respond(alert: EmergencyAlertData) {
    setBusyId(alert.id);
    setError("");
    try {
      const response = await fetch(
        `${API_BASE}/api/emergency/alerts/${alert.id}/acknowledge`,
        { method: "PATCH", headers: { "X-Staff-Email": email } },
      );
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(
          typeof data.detail === "string" ? data.detail : "Could not confirm. Try again.",
        );
      }
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not confirm. Try again.");
    } finally {
      setBusyId(null);
    }
  }

  if (!active) return null;

  return (
    <div className="em-overlay" role="alertdialog" aria-modal="true" aria-labelledby="em-title">
      <div className="em-panel">
        <div className="em-panel-head">
          <span className="em-siren-icon">
            <Siren size={30} />
          </span>
          <div>
            <p className="em-kicker">EMERGENCY · CODE RED</p>
            <h2 id="em-title">Critical patient arriving</h2>
          </div>
        </div>

        {alerts.map((alert) => (
          <div className="em-alert-card" key={alert.id}>
            <div className="em-alert-type">{alert.emergency_label}</div>
            <dl className="em-facts">
              <div>
                <dt>Patient</dt>
                <dd>{alert.patient_label}</dd>
              </div>
              {alert.location && (
                <div>
                  <dt>Location</dt>
                  <dd>{alert.location}</dd>
                </div>
              )}
              <div>
                <dt>Paged as</dt>
                <dd>{alert.required_specialty}</dd>
              </div>
              <div>
                <dt>Raised by</dt>
                <dd>{alert.raised_by}</dd>
              </div>
            </dl>
            {alert.notes && <p className="em-notes">{alert.notes}</p>}
            <p className="em-team">
              Also paged: {alert.paged_doctors.map((d) => d.name).join(", ")}
            </p>
            <button
              type="button"
              className="em-respond"
              disabled={busyId === alert.id}
              onClick={() => respond(alert)}
            >
              {busyId === alert.id ? "Confirming..." : "I'm responding"}
            </button>
          </div>
        ))}

        {error && <p className="em-error" role="alert">{error}</p>}

        <div className="em-panel-foot">
          <button
            type="button"
            className="em-mute"
            onClick={() => setMutedFor(muted ? null : newest.id)}
          >
            <VolumeX size={16} />
            {muted ? "Turn siren back on" : "Silence siren"}
          </button>
          {blocked && (
            <span className="em-hint">Click anywhere on the page to enable the siren sound.</span>
          )}
        </div>
      </div>
    </div>
  );
}

export default EmergencyDoctor;
