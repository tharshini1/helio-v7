import { useEffect, useState } from "react";

import { API_BASE } from "../config";
import DischargeSheet from "../components/DischargeSheet";
import type { DischargeData } from "../components/DischargeSheet";

type Patient = { id: number; patient_code: string; name: string; status: string };

export default function Discharge() {
  const role = localStorage.getItem("helio_role") || "";
  const email = localStorage.getItem("helio_email") || "";
  const isDoctor = role === "Doctor";

  const [discharges, setDischarges] = useState<DischargeData[]>([]);
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<Patient[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [amounts, setAmounts] = useState<Record<number, string>>({});
  const [meds, setMeds] = useState<Record<number, string>>({});
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/discharges`);
      if (res.ok) setDischarges(await res.json());
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    if (!query.trim()) {
      setSuggestions([]);
      return;
    }
    const h = setTimeout(async () => {
      try {
        const res = await fetch(`${API_BASE}/api/patients/search?q=${encodeURIComponent(query.trim())}`);
        if (res.ok) {
          const rows: Patient[] = await res.json();
          setSuggestions(rows.filter((p) => p.status !== "DISCHARGED"));
        }
      } catch (e) {
        console.error(e);
      }
    }, 250);
    return () => clearTimeout(h);
  }, [query]);

  const call = async (url: string, init: RequestInit, okMsg: string) => {
    setBusy(true);
    setMessage("");
    try {
      const res = await fetch(`${API_BASE}${url}`, {
        ...init,
        headers: { "Content-Type": "application/json", "X-Staff-Email": email, ...(init.headers || {}) },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Request failed.");
      setMessage(okMsg);
      await load();
      return data;
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Request failed.");
    } finally {
      setBusy(false);
    }
  };

  const draft = async (p: Patient) => {
    setQuery("");
    setSuggestions([]);
    const data = await call(`/api/discharges/draft/${p.id}`, { method: "POST" },
      `Discharge Agent drafted the summary for ${p.patient_code}. Enter the amount, then a doctor can approve.`);
    if (data) setSelectedId(data.discharge.id);
  };

  const saveAmount = (d: DischargeData) => {
    const value = Number(amounts[d.id]);
    if (!amounts[d.id] || Number.isNaN(value) || value < 0) {
      setMessage("Enter a valid amount.");
      return;
    }
    call(`/api/discharges/${d.id}/amount`, { method: "PATCH", body: JSON.stringify({ amount: value }) }, "Amount saved.");
  };

  const approve = (d: DischargeData) =>
    call(`/api/discharges/${d.id}/approve`, {
      method: "PATCH",
      body: JSON.stringify({ medication: meds[d.id] ?? null }),
    }, "Discharge approved. Bed released.");

  const reject = (d: DischargeData) =>
    call(`/api/discharges/${d.id}/reject`, { method: "PATCH" }, "Discharge rejected.");

  const pending = discharges.filter((d) => d.status === "PENDING");
  const selected = discharges.find((d) => d.id === selectedId) || null;

  return (
    <div className="page-container">
      <div className="page-header">
        <div>
          <h1>Discharge Summary</h1>
          <p>
            The Discharge Agent fills the sheet automatically. Only the amount is entered by staff,
            and only a doctor can approve.
          </p>
        </div>
      </div>

      {!isDoctor && (
        <div className="role-notice">
          <strong>Doctor approval required</strong>
          <span>You can prepare the summary and enter the amount; a doctor must approve it.</span>
        </div>
      )}

      <section className="resource-panel">
        <div className="patient-search">
          <label>
            Generate discharge summary — search patient by ID or name
            <input type="text" placeholder="e.g. P012 or Kumar" value={query}
              onChange={(e) => setQuery(e.target.value)} />
          </label>
          {suggestions.length > 0 && (
            <ul className="patient-suggestions">
              {suggestions.map((s) => (
                <li key={s.id} onClick={() => draft(s)}>{s.name} — {s.patient_code}</li>
              ))}
            </ul>
          )}
        </div>
        {message && <div className="system-message">{message}</div>}
      </section>

      <section className="resource-panel">
        <h3>Pending approval ({pending.length})</h3>
        {pending.length === 0 && <div className="table-secondary">No pending discharge summaries.</div>}
        {pending.map((d) => (
          <div key={d.id} className="portal-card">
            <DischargeSheet d={{ ...d, medication: meds[d.id] ?? d.medication }} />

            <div className="form-row">
              <label>
                Amount (₹) — entered by staff
                <input type="number" min={0} value={amounts[d.id] ?? (d.amount ?? "")}
                  onChange={(e) => setAmounts({ ...amounts, [d.id]: e.target.value })} />
              </label>
              <button className="secondary-button" disabled={busy} onClick={() => saveAmount(d)}>
                Save Amount
              </button>
            </div>

            {isDoctor && (
              <>
                <label>
                  Medication (agent draft — doctor may correct)
                  <textarea rows={3} value={meds[d.id] ?? d.medication ?? ""}
                    onChange={(e) => setMeds({ ...meds, [d.id]: e.target.value })} />
                </label>
                <div className="sheet-actions">
                  <button className="primary-button" disabled={busy || d.amount === null} onClick={() => approve(d)}>
                    Approve Discharge
                  </button>
                  <button className="reject-button" disabled={busy} onClick={() => reject(d)}>Reject</button>
                </div>
                {d.amount === null && <div className="table-secondary">Amount must be entered before approval.</div>}
              </>
            )}
          </div>
        ))}
      </section>

      <section className="resource-panel">
        <h3>Discharge history</h3>
        <table className="appointment-table">
          <thead>
            <tr><th>Patient</th><th>Doctor</th><th>Discharge date</th><th>Amount</th><th>Status</th><th></th></tr>
          </thead>
          <tbody>
            {discharges.filter((d) => d.status !== "PENDING").map((d) => (
              <tr key={d.id}>
                <td>{d.patient_code} · {d.patient_name}</td>
                <td>{d.doctor_name ?? "—"}</td>
                <td>{d.discharge_date ?? "—"}</td>
                <td>{d.amount === null ? "—" : `₹ ${d.amount.toFixed(2)}`}</td>
                <td>{d.status}</td>
                <td><button className="secondary-button" onClick={() => setSelectedId(d.id)}>View sheet</button></td>
              </tr>
            ))}
          </tbody>
        </table>
        {selected && selected.status !== "PENDING" && (
          <>
            <DischargeSheet d={selected} />
            <div className="sheet-actions">
              <button className="secondary-button" onClick={() => window.print()}>Print</button>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
