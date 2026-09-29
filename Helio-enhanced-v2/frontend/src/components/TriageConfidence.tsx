export type TriageInfo = {
  priority: string;
  confidence?: number;
  confidence_pct?: number;
  confidence_level?: "HIGH" | "MEDIUM" | "LOW";
  needs_review?: boolean;
  confidence_factors?: string[];
  reasoning?: string;
  recommended_action?: string;
};

/** Triage Agent result with its confidence score. */
export default function TriageConfidence({ triage }: { triage?: TriageInfo | null }) {
  if (!triage) return null;

  const pct = triage.confidence_pct ?? Math.round((triage.confidence ?? 0) * 100);
  const level = triage.confidence_level ?? (pct >= 80 ? "HIGH" : pct >= 60 ? "MEDIUM" : "LOW");
  const tone = level === "HIGH" ? "high" : level === "LOW" ? "low" : "";

  return (
    <div className="triage-conf">
      <div className="triage-conf-head">
        <span className="ba-eyebrow">TRIAGE AGENT</span>
        <span className={`ba-priority ${triage.priority.toLowerCase()}`}>{triage.priority}</span>
      </div>

      <div className="ai-confidence">
        <span>
          Confidence <strong>{pct}%</strong> · {level.toLowerCase()}
        </span>
        <div className={`ai-confidence-bar ${tone}`}>
          <span style={{ width: `${pct}%` }} />
        </div>
      </div>

      {triage.needs_review && (
        <div className="ba-warning">
          Low confidence — a clinician should review this triage priority before acting on it.
        </div>
      )}

      {triage.confidence_factors && triage.confidence_factors.length > 0 && (
        <ul className="triage-conf-factors">
          {triage.confidence_factors.map((f) => (
            <li key={f}>{f}</li>
          ))}
        </ul>
      )}

      {triage.reasoning && <p className="ba-reason">{triage.reasoning}</p>}
    </div>
  );
}
