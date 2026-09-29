import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { CalendarClock, DoorOpen, LayoutDashboard, LogOut, Search, Stethoscope } from "lucide-react";

import { API_BASE } from "../config";
import DischargeSheet from "../components/DischargeSheet";
import type { DischargeData } from "../components/DischargeSheet";

type Props = { patientId: number; onLogout: () => void };
type Tab = "Overview" | "Book Appointment" | "Doctor Availability" | "Discharge Summary";

type Patient = {
  id: number; patient_code: string; name: string; age: number | null; gender: string | null;
  symptoms: string | null; heart_rate: number | null; spo2: number | null;
  temperature: number | null; status: string;
};
type Doctor = { id: number; name: string; specialization: string; years_experience: number | null; is_available: boolean };
type Appt = {
  id: number; doctor_name: string; specialization: string;
  appointment_date: string; appointment_time: string; reason: string; status: string;
};
type Rec = { specialization: string | null; recommended_doctor: Doctor | null; alternatives: Doctor[]; reason: string };

const pad = (n: number) => String(n).padStart(2, "0");
const today = () => { const d = new Date(); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`; };
const nowTime = () => { const d = new Date(); return `${pad(d.getHours())}:${pad(d.getMinutes())}`; };
const show = (x: unknown, u = "") => (x === null || x === undefined || x === "" ? "—" : `${x}${u}`);
const initials = (name: string) =>
  name.replace(/^(dr\.?|nurse)\s+/i, "").trim().charAt(0).toUpperCase() || "?";

const TABS: { label: Tab; icon: ReactNode; title: string; subtitle: string }[] = [
  { label: "Overview", icon: <LayoutDashboard size={18} />, title: "Overview", subtitle: "Your health record and appointments at a glance." },
  { label: "Book Appointment", icon: <CalendarClock size={18} />, title: "Book an appointment", subtitle: "The Appointment Agent suggests the right doctor for you." },
  { label: "Doctor Availability", icon: <Stethoscope size={18} />, title: "Doctor availability", subtitle: "Filter doctors by availability, specialty and experience." },
  { label: "Discharge Summary", icon: <DoorOpen size={18} />, title: "Discharge summary", subtitle: "Available once your doctor approves your discharge." },
];

export default function PatientPortal({ patientId, onLogout }: Props) {
  const [tab, setTab] = useState<Tab>("Overview");
  const [patient, setPatient] = useState<Patient | null>(null);
  const [doctors, setDoctors] = useState<Doctor[]>([]);
  const [appts, setAppts] = useState<Appt[]>([]);
  const [summaries, setSummaries] = useState<DischargeData[]>([]);
  const [rec, setRec] = useState<Rec | null>(null);

  const [doctorId, setDoctorId] = useState("");
  const [pickedDoctor, setPickedDoctor] = useState<Doctor | null>(null);
  const [date, setDate] = useState("");
  const [time, setTime] = useState("");
  const [reason, setReason] = useState("");
  const [msg, setMsg] = useState("");
  const [msgKind, setMsgKind] = useState<"ok" | "error">("ok");
  const [busy, setBusy] = useState(false);

  // Doctor availability filters
  const [fSearch, setFSearch] = useState("");
  const [fStatus, setFStatus] = useState<"all" | "available" | "unavailable">("all");
  const [fSpec, setFSpec] = useState("all");
  const [fExp, setFExp] = useState("any");
  const [fSort, setFSort] = useState<"name" | "experience" | "availability">("availability");

  const load = async () => {
    try {
      const [p, d, a, s] = await Promise.all([
        fetch(`${API_BASE}/api/patients/${patientId}`),
        fetch(`${API_BASE}/api/doctors`),
        fetch(`${API_BASE}/api/appointments?patient_id=${patientId}`),
        fetch(`${API_BASE}/api/discharges?patient_id=${patientId}`),
      ]);
      if (p.ok) {
        const pd: Patient = await p.json();
        setPatient(pd);
        setReason((r) => r || (pd.symptoms && pd.symptoms !== "No symptoms" ? pd.symptoms : ""));
      }
      if (d.ok) setDoctors(await d.json());
      if (a.ok) setAppts(await a.json());
      if (s.ok) setSummaries(await s.json());
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    load();
    fetch(`${API_BASE}/api/appointments/recommend/${patientId}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((r: Rec | null) => {
        if (r) {
          setRec(r);
          if (r.recommended_doctor) setDoctorId((current) => current || String(r.recommended_doctor!.id));
        }
      })
      .catch(console.error);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [patientId]);

  const notify = (text: string, kind: "ok" | "error" = "ok") => {
    setMsg(text);
    setMsgKind(kind);
  };

  const book = async () => {
    setMsg("");
    if (!doctorId || !date || !time || !reason.trim()) {
      notify("Please choose a doctor, date, time and reason.", "error");
      return;
    }
    if (date < today() || (date === today() && time <= nowTime())) {
      notify("Please choose a future date and time.", "error");
      return;
    }
    setBusy(true);
    try {
      const res = await fetch(`${API_BASE}/api/appointments`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          patient_id: patientId, doctor_id: Number(doctorId),
          appointment_date: date, appointment_time: time, reason: reason.trim(),
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Booking failed.");
      notify("Appointment booked successfully.");
      setDate(""); setTime("");
      await load();
    } catch (e) {
      notify(e instanceof Error ? e.message : "Booking failed.", "error");
    } finally {
      setBusy(false);
    }
  };

  // Doctors offered on the booking form: the agent's picks, plus any doctor
  // the patient chose from the availability list.
  const choices = useMemo(() => {
    const base = rec?.recommended_doctor ? [rec.recommended_doctor, ...rec.alternatives] : [];
    if (pickedDoctor && !base.some((d) => d.id === pickedDoctor.id)) base.push(pickedDoctor);
    return base;
  }, [rec, pickedDoctor]);

  const approved = summaries.filter((s) => s.status === "APPROVED");
  const upcoming = appts.filter((a) => a.status === "SCHEDULED");

  const specializations = useMemo(
    () => Array.from(new Set(doctors.map((d) => d.specialization))).sort(),
    [doctors],
  );

  const filteredDoctors = useMemo(() => {
    const term = fSearch.trim().toLowerCase();
    const minYears = fExp === "any" ? 0 : Number(fExp);
    const list = doctors.filter((d) => {
      if (fStatus === "available" && !d.is_available) return false;
      if (fStatus === "unavailable" && d.is_available) return false;
      if (fSpec !== "all" && d.specialization !== fSpec) return false;
      if ((d.years_experience ?? 0) < minYears) return false;
      if (term && !`${d.name} ${d.specialization}`.toLowerCase().includes(term)) return false;
      return true;
    });
    return [...list].sort((a, b) => {
      if (fSort === "experience") return (b.years_experience ?? 0) - (a.years_experience ?? 0);
      if (fSort === "availability" && a.is_available !== b.is_available) return a.is_available ? -1 : 1;
      return a.name.localeCompare(b.name);
    });
  }, [doctors, fSearch, fStatus, fSpec, fExp, fSort]);

  const availableCount = doctors.filter((d) => d.is_available).length;
  const filtersActive = fSearch || fStatus !== "all" || fSpec !== "all" || fExp !== "any";
  const resetFilters = () => {
    setFSearch(""); setFStatus("all"); setFSpec("all"); setFExp("any");
  };

  const bookWith = (d: Doctor) => {
    setPickedDoctor(d);
    setDoctorId(String(d.id));
    setMsg("");
    setTab("Book Appointment");
  };

  const current = TABS.find((t) => t.label === tab)!;

  return (
    <div className="pp-shell">
      {/* ------------------------------ SIDEBAR ------------------------------ */}
      <aside className="pp-sidebar">
        <div className="pp-brand">
          <div className="pp-mark">H</div>
          <div>
            <h1>Helio</h1>
            <span>Patient portal</span>
          </div>
        </div>

        <div className="pp-user">
          <div className="pp-avatar">{patient ? initials(patient.name) : "…"}</div>
          <div className="pp-user-text">
            <strong>{patient ? patient.name : "Loading..."}</strong>
            <span>{patient ? patient.patient_code : ""}</span>
          </div>
        </div>

        <nav className="pp-nav" aria-label="Patient portal">
          {TABS.map((t) => (
            <button
              key={t.label}
              type="button"
              className={tab === t.label ? "active" : ""}
              onClick={() => { setTab(t.label); setMsg(""); }}
            >
              <span className="pp-nav-icon">{t.icon}</span>
              <span className="pp-nav-label">{t.label}</span>
              {t.label === "Discharge Summary" && approved.length > 0 && (
                <span className="pp-nav-badge">{approved.length}</span>
              )}
              {t.label === "Overview" && upcoming.length > 0 && (
                <span className="pp-nav-badge">{upcoming.length}</span>
              )}
            </button>
          ))}
        </nav>

        <div className="pp-side-footer">
          <button type="button" className="pp-logout" onClick={onLogout}>
            <LogOut size={17} />
            <span>Logout</span>
          </button>
        </div>
      </aside>

      {/* -------------------------------- MAIN -------------------------------- */}
      <main className="pp-main">
        <header className="pp-header">
          <span className="pp-eyebrow">PATIENT PORTAL</span>
          <h2>{current.title}</h2>
          <p>{current.subtitle}</p>
        </header>

        {/* ---------------------------- OVERVIEW ---------------------------- */}
        {tab === "Overview" && patient && (
          <>
            <div className="pp-tiles">
              <div className="pp-tile">
                <span>Status</span>
                <strong>{show(patient.status)}</strong>
              </div>
              <div className="pp-tile">
                <span>Upcoming appointments</span>
                <strong>{upcoming.length}</strong>
              </div>
              <div className="pp-tile">
                <span>Doctors available now</span>
                <strong>{availableCount}</strong>
              </div>
            </div>

            <div className="pp-card">
              <h4>My health record</h4>
              <div className="pp-record">
                <div><span>Age</span><strong>{show(patient.age)}</strong></div>
                <div><span>Gender</span><strong>{show(patient.gender)}</strong></div>
                <div><span>Heart rate</span><strong>{show(patient.heart_rate, " bpm")}</strong></div>
                <div><span>SpO₂</span><strong>{show(patient.spo2, "%")}</strong></div>
                <div><span>Temperature</span><strong>{show(patient.temperature, "°C")}</strong></div>
                <div className="wide"><span>Symptoms</span><strong>{show(patient.symptoms)}</strong></div>
              </div>
            </div>

            <div className="pp-card">
              <div className="pp-card-head">
                <h4>My appointments</h4>
                <button type="button" className="pp-link" onClick={() => setTab("Book Appointment")}>
                  + Book new
                </button>
              </div>
              {appts.length === 0 ? (
                <div className="pp-empty">No appointments yet.</div>
              ) : (
                <div className="pp-table-wrap">
                  <table className="pp-table">
                    <thead><tr><th>Doctor</th><th>Date</th><th>Time</th><th>Status</th></tr></thead>
                    <tbody>
                      {appts.map((a) => (
                        <tr key={a.id}>
                          <td>
                            <strong>{a.doctor_name}</strong>
                            <span className="pp-sub">{a.specialization}</span>
                          </td>
                          <td>{a.appointment_date}</td>
                          <td>{a.appointment_time}</td>
                          <td>
                            <span className={`appointment-status ${a.status.toLowerCase()}`}>
                              {a.status.replaceAll("_", " ")}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </>
        )}

        {/* ------------------------ BOOK APPOINTMENT ------------------------ */}
        {tab === "Book Appointment" && (
          <div className="pp-book">
            <div className="pp-card pp-book-form">
              <h4>Appointment details</h4>

              {choices.length > 0 ? (
                <>
                  <div className="pp-field">
                    <span className="pp-label">Choose your doctor</span>
                    <div className="pp-doctor-picks" role="radiogroup" aria-label="Doctor">
                      {choices.map((d) => {
                        const isRec = rec?.recommended_doctor?.id === d.id;
                        return (
                          <button
                            key={d.id}
                            type="button"
                            role="radio"
                            aria-checked={doctorId === String(d.id)}
                            className={`pp-doctor-pick ${doctorId === String(d.id) ? "selected" : ""}`}
                            onClick={() => setDoctorId(String(d.id))}
                          >
                            <span className="pp-doc-avatar">{initials(d.name)}</span>
                            <span className="pp-doc-text">
                              <strong>{d.name}</strong>
                              <small>
                                {d.specialization}
                                {d.years_experience ? ` · ${d.years_experience} yrs` : ""}
                              </small>
                            </span>
                            {isRec && <span className="pp-tag">Recommended</span>}
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  <div className="pp-grid-2">
                    <label className="pp-field">
                      <span className="pp-label">Date</span>
                      <input type="date" min={today()} value={date} onChange={(e) => setDate(e.target.value)} />
                    </label>
                    <label className="pp-field">
                      <span className="pp-label">Time</span>
                      <input type="time" value={time} onChange={(e) => setTime(e.target.value)} />
                    </label>
                  </div>

                  <label className="pp-field">
                    <span className="pp-label">Reason for visit</span>
                    <textarea
                      rows={4}
                      placeholder="Describe your symptoms or the reason for this visit"
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                    />
                  </label>

                  <button type="button" className="pp-primary" disabled={busy} onClick={book}>
                    {busy ? "Booking..." : "Book appointment"}
                  </button>
                </>
              ) : (
                <div className="pp-empty">
                  No doctor is currently available for booking. Please check the{" "}
                  <button type="button" className="pp-link" onClick={() => setTab("Doctor Availability")}>
                    doctor availability
                  </button>{" "}
                  list or try again later.
                </div>
              )}

              {msg && <div className={`pp-message ${msgKind}`} role="status">{msg}</div>}
            </div>

            <aside className="pp-card pp-agent">
              <span className="pp-eyebrow">APPOINTMENT AGENT</span>
              {rec ? (
                <>
                  <h4>{rec.recommended_doctor ? rec.recommended_doctor.name : "No suitable doctor available"}</h4>
                  {rec.recommended_doctor && (
                    <p className="pp-agent-meta">
                      {rec.specialization || rec.recommended_doctor.specialization}
                      {rec.recommended_doctor.years_experience
                        ? ` · ${rec.recommended_doctor.years_experience} yrs experience`
                        : ""}
                    </p>
                  )}
                  <p className="pp-agent-reason">{rec.reason}</p>
                </>
              ) : (
                <p className="pp-agent-reason">The agent is preparing a recommendation…</p>
              )}
              <ul className="pp-tips">
                <li>Pick a future date and time.</li>
                <li>Only available doctors can be booked.</li>
                <li>Your appointment appears under Overview once booked.</li>
              </ul>
            </aside>
          </div>
        )}

        {/* ---------------------- DOCTOR AVAILABILITY ---------------------- */}
        {tab === "Doctor Availability" && (
          <>
            <div className="pp-card pp-filters">
              <div className="pp-filter-row">
                <div className="pp-search">
                  <Search size={16} />
                  <input
                    type="search"
                    placeholder="Search by doctor or specialty"
                    value={fSearch}
                    onChange={(e) => setFSearch(e.target.value)}
                  />
                </div>

                <div className="pp-chips" role="group" aria-label="Availability">
                  {([
                    ["all", `All (${doctors.length})`],
                    ["available", `Available (${availableCount})`],
                    ["unavailable", `Unavailable (${doctors.length - availableCount})`],
                  ] as const).map(([value, label]) => (
                    <button
                      key={value}
                      type="button"
                      className={fStatus === value ? "active" : ""}
                      onClick={() => setFStatus(value)}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="pp-filter-row">
                <label className="pp-select">
                  <span>Specialty</span>
                  <select value={fSpec} onChange={(e) => setFSpec(e.target.value)}>
                    <option value="all">All specialties</option>
                    {specializations.map((s) => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                </label>

                <label className="pp-select">
                  <span>Experience</span>
                  <select value={fExp} onChange={(e) => setFExp(e.target.value)}>
                    <option value="any">Any</option>
                    <option value="5">5+ years</option>
                    <option value="10">10+ years</option>
                    <option value="15">15+ years</option>
                  </select>
                </label>

                <label className="pp-select">
                  <span>Sort by</span>
                  <select value={fSort} onChange={(e) => setFSort(e.target.value as typeof fSort)}>
                    <option value="availability">Availability</option>
                    <option value="experience">Experience</option>
                    <option value="name">Name</option>
                  </select>
                </label>

                {filtersActive && (
                  <button type="button" className="pp-reset" onClick={resetFilters}>
                    Reset filters
                  </button>
                )}
              </div>
            </div>

            <div className="pp-result-count">
              Showing {filteredDoctors.length} of {doctors.length} doctors
            </div>

            {filteredDoctors.length === 0 ? (
              <div className="pp-card pp-empty">No doctors match these filters.</div>
            ) : (
              <div className="pp-doctor-grid">
                {filteredDoctors.map((d) => (
                  <div key={d.id} className={`pp-doctor-card ${d.is_available ? "" : "off"}`}>
                    <div className="pp-doctor-top">
                      <span className="pp-doc-avatar large">{initials(d.name)}</span>
                      <span className={`pp-avail ${d.is_available ? "on" : "off"}`}>
                        <i /> {d.is_available ? "Available" : "Unavailable"}
                      </span>
                    </div>
                    <h5>{d.name}</h5>
                    <p>{d.specialization}</p>
                    <small>{d.years_experience ? `${d.years_experience} years experience` : "Experience not listed"}</small>
                    <button
                      type="button"
                      className="pp-book-btn"
                      disabled={!d.is_available}
                      onClick={() => bookWith(d)}
                    >
                      {d.is_available ? "Book appointment" : "Not bookable"}
                    </button>
                  </div>
                ))}
              </div>
            )}
          </>
        )}

        {/* ----------------------- DISCHARGE SUMMARY ----------------------- */}
        {tab === "Discharge Summary" && (
          <div>
            {approved.length === 0 ? (
              <div className="pp-card">
                <div className="pp-empty">
                  No discharge summary yet. It appears here once your doctor approves your discharge.
                </div>
              </div>
            ) : (
              approved.map((s) => (
                <div key={s.id}>
                  <DischargeSheet d={s} />
                  <div className="sheet-actions">
                    <button className="secondary-button" onClick={() => window.print()}>Print / Save as PDF</button>
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </main>
    </div>
  );
}
