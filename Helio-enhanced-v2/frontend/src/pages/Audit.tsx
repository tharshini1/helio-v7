import { useEffect, useMemo, useState } from "react";

import { API_BASE } from "../config";

type AuditLog = {
  id: number;
  patient_id: number | null;
  patient_code?: string | null;
  action: string;
  agent: string | null;
  status: string;
  details: string | null;
  created_at: string | null;
};

// Audit timestamps are stored in UTC without a zone marker; treat them as UTC
// so they display correctly in the viewer's local time.
const toDate = (value: string | null) => {
  if (!value) return null;
  const hasZone = /[zZ]|[+-]\d{2}:?\d{2}$/.test(value);
  const date = new Date(hasZone ? value : `${value}Z`);
  return Number.isNaN(date.getTime()) ? null : date;
};

const parseDetails = (raw: string | null): [string, string][] => {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return Object.entries(parsed as Record<string, unknown>).map(([key, value]) => [
        key.replaceAll("_", " "),
        value === null || value === undefined || value === ""
          ? "—"
          : typeof value === "object"
            ? JSON.stringify(value)
            : String(value),
      ]);
    }
    return [["details", String(parsed)]];
  } catch {
    return [["details", raw]];
  }
};

const statusClass = (status: string) => {
  const s = (status || "").toUpperCase();
  if (s.includes("REJECT") || s.includes("DENIED") || s.includes("FAIL")) return "rejected";
  if (s.includes("APPROVED") || s === "EXECUTED" || s === "COMPLETED" || s === "AUTO") return "approved";
  return "pending";
};

export default function Audit() {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const [search, setSearch] = useState("");
  const [agentFilter, setAgentFilter] = useState("ALL");
  const [statusFilter, setStatusFilter] = useState("ALL");

  const loadAuditLogs = async () => {
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE}/api/audit`);

      if (!response.ok) {
        throw new Error(
          response.status === 404
            ? "The audit service is not available on this server."
            : "Unable to load audit records."
        );
      }

      const data = await response.json();
      setLogs(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to load audit records."
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAuditLogs();
  }, []);

  const agents = useMemo(
    () => Array.from(new Set(logs.map((l) => l.agent || "System"))).sort(),
    [logs]
  );

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    return logs.filter((log) => {
      if (agentFilter !== "ALL" && (log.agent || "System") !== agentFilter) return false;
      if (statusFilter !== "ALL" && statusClass(log.status) !== statusFilter) return false;
      if (!term) return true;
      const haystack = [
        log.action,
        log.agent,
        log.status,
        log.details,
        log.patient_code,
        log.patient_id ? `#${log.patient_id}` : "",
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(term);
    });
  }, [logs, search, agentFilter, statusFilter]);

  const agentActions = logs.filter(
    (log) => log.agent && log.agent.toLowerCase() !== "system"
  ).length;
  const approved = logs.filter((log) => log.status?.toUpperCase().includes("APPROVED")).length;
  const executed = logs.filter((log) =>
    ["EXECUTED", "COMPLETED"].includes(log.status?.toUpperCase())
  ).length;

  const filtersActive = search || agentFilter !== "ALL" || statusFilter !== "ALL";

  return (
    <div className="page-container">
      <div className="page-header">
        <div>
          <h1>Audit Trail</h1>
          <p>
            Every action recorded across Helio: agent decisions, approvals,
            bookings, sign-ins and executed changes.
          </p>
        </div>

        <div className="audit-badge">AUDIT LOG ACTIVE</div>
      </div>

      <div className="stats-grid">
        <div className="stat-card">
          <span>Total Events</span>
          <strong>{logs.length}</strong>
        </div>

        <div className="stat-card">
          <span>Agent Actions</span>
          <strong>{agentActions}</strong>
        </div>

        <div className="stat-card">
          <span>Approved Actions</span>
          <strong>{approved}</strong>
        </div>

        <div className="stat-card">
          <span>Executed Actions</span>
          <strong>{executed}</strong>
        </div>
      </div>

      <div className="content-card">
        <div className="section-heading">
          <div>
            <h2>System Activity</h2>
            <p>Chronological record of Helio operations, newest first.</p>
          </div>

          <button
            className="secondary-button"
            onClick={loadAuditLogs}
            disabled={loading}
          >
            {loading ? "Loading..." : "Refresh"}
          </button>
        </div>

        <div className="audit-filters">
          <input
            type="search"
            placeholder="Search action, agent, patient or details"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />

          <select value={agentFilter} onChange={(e) => setAgentFilter(e.target.value)}>
            <option value="ALL">All agents</option>
            {agents.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>

          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="ALL">All outcomes</option>
            <option value="approved">Approved / executed</option>
            <option value="pending">Pending</option>
            <option value="rejected">Rejected / denied</option>
          </select>

          {filtersActive && (
            <button
              type="button"
              className="secondary-button"
              onClick={() => {
                setSearch("");
                setAgentFilter("ALL");
                setStatusFilter("ALL");
              }}
            >
              Clear
            </button>
          )}
        </div>

        {logs.length > 0 && (
          <div className="audit-count">
            Showing {filtered.length} of {logs.length} records
          </div>
        )}

        {error && <div className="error-message">{error}</div>}

        {loading && logs.length === 0 ? (
          <div className="empty-state">Loading audit records...</div>
        ) : logs.length === 0 && !error ? (
          <div className="empty-state">No audit records available yet.</div>
        ) : filtered.length === 0 && logs.length > 0 ? (
          <div className="empty-state">No records match these filters.</div>
        ) : (
          <div className="audit-list">
            {filtered.map((log) => {
              const when = toDate(log.created_at);
              const details = parseDetails(log.details);

              return (
                <div className="audit-row" key={log.id}>
                  <div className="audit-time">
                    {when ? (
                      <>
                        <strong>{when.toLocaleDateString()}</strong>
                        <span>{when.toLocaleTimeString()}</span>
                      </>
                    ) : (
                      "--"
                    )}
                  </div>

                  <div className="audit-indicator">
                    <span></span>
                  </div>

                  <div className="audit-content">
                    <div className="audit-title-row">
                      <h3>
                        {log.action?.replaceAll("_", " ") || "System Action"}
                      </h3>

                      <span className={`status-badge ${statusClass(log.status)}`}>
                        {(log.status || "UNKNOWN").replaceAll("_", " ")}
                      </span>
                    </div>

                    {details.length > 0 ? (
                      <div className="audit-details">
                        {details.map(([key, value]) => (
                          <span key={key} className="audit-chip">
                            <em>{key}</em> {value}
                          </span>
                        ))}
                      </div>
                    ) : (
                      <p>No additional details.</p>
                    )}

                    <div className="audit-meta">
                      <span>Agent: {log.agent || "System"}</span>

                      <span>
                        Patient:{" "}
                        {log.patient_code
                          ? log.patient_code
                          : log.patient_id
                            ? `#${log.patient_id}`
                            : "N/A"}
                      </span>

                      <span>Event #{log.id}</span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div className="audit-footer-card">
        <strong>Traceability</strong>
        <span>
          Helio records operational events to support transparency,
          human oversight and post-event review.
        </span>
      </div>
    </div>
  );
}
