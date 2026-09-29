import { useEffect, useState } from "react";

import { API_BASE } from "../config";
import TriageConfidence, { type TriageInfo } from "./TriageConfidence";

type Recommendation = {
  status: string;
  bed?: string;
  triage?: TriageInfo;
  resource?: {
    category: string;
    required_ward: string;
    recommended_bed: string | null;
    available: boolean;
    reason: string;
  };
};

type Props = {
  appointmentId: number;
  patientName: string;
  email: string;
  onClose: () => void;
  onDone: (message: string) => void;
};

/** After the visit: does the patient need a bed? If so, allocate the recommended one. */
export default function BedDecisionDialog({ appointmentId, patientName, email, onClose, onDone }: Props) {
  const [rec, setRec] = useState<Recommendation | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/api/appointments/${appointmentId}/bed-recommendation`, {
          headers: { "X-Staff-Email": email },
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Could not load the bed recommendation.");
        setRec(data);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not load the bed recommendation.");
      } finally {
        setLoading(false);
      }
    })();
  }, [appointmentId, email]);

  async function decide(bedNeeded: boolean) {
    setSaving(true);
    setError("");
    try {
      const res = await fetch(`${API_BASE}/api/appointments/${appointmentId}/bed-decision`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Staff-Email": email },
        body: JSON.stringify({
          bed_needed: bedNeeded,
          bed_code: bedNeeded ? rec?.resource?.recommended_bed ?? null : null,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Could not save the bed decision.");

      if (data.status === "ALLOCATED") onDone(`✓ ${data.allocation.bed} allocated to ${data.patient.code}`);
      else if (data.status === "NO_BED_NEEDED") onDone("Recorded: no bed needed for this visit.");
      else if (data.status === "NO_BED_AVAILABLE") onDone("Bed needed, but none is free right now. Human intervention required.");
      else throw new Error(data.message || data.error || "Bed allocation failed.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save the bed decision.");
      setSaving(false);
    }
  }

  const r = rec?.resource;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="appointment-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <span className="eyebrow">AFTER VISIT</span>
            <h3>Is a bed needed for {patientName}?</h3>
          </div>
          <button className="modal-close" onClick={onClose}>×</button>
        </div>

        <div className="booking-form">
          {loading && <div className="ba-loading">Triage and Bed Agents are analysing the patient…</div>}

          {rec?.status === "ALREADY_ALLOCATED" && (
            <div className="ba-message ok">This patient already occupies bed {rec.bed}.</div>
          )}

          {rec?.status === "COMPLETED" && (
            <>
              <TriageConfidence triage={rec.triage} />

              {r && (
                <div className="ba-reco">
                  <div className="ba-reco-grid bed-decision-grid">
                    <div><span>Category</span><strong>{r.category}</strong></div>
                    <div><span>Ward</span><strong>{r.required_ward}</strong></div>
                    <div><span>Bed</span><strong>{r.recommended_bed ?? "None free"}</strong></div>
                  </div>
                  <p className="ba-reason">{r.reason}</p>
                  {!r.available && (
                    <div className="ba-warning">
                      No bed is free in this ward. If you record that a bed is needed, it is
                      logged for human follow-up; the patient is not moved to another ward.
                    </div>
                  )}
                </div>
              )}
            </>
          )}

          {error && <div className="appointment-message error">{error}</div>}

          <div className="booking-actions">
            <button className="secondary-button" onClick={onClose} disabled={saving}>Decide later</button>
            {rec?.status === "COMPLETED" && (
              <>
                <button className="secondary-button" onClick={() => decide(false)} disabled={saving}>
                  No bed needed
                </button>
                <button className="primary-button" onClick={() => decide(true)} disabled={saving}>
                  {saving
                    ? "Saving..."
                    : r?.available
                      ? `Bed needed — allocate ${r.recommended_bed}`
                      : "Bed needed (none free)"}
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
