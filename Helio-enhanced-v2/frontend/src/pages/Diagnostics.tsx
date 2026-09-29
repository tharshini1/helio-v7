import { useEffect, useState } from "react";

import { API_BASE } from "../config";

interface Patient {
  id: number;
  patient_code: string;
  name: string;
  status: string;
}

interface DoctorOption {
  id: number;
  name: string;
  specialization: string;
}

interface AiReport {
  available: boolean;
  problem: string | null;
  reason: string | null;
  confidence: number | null;
  urgency: string | null;
  findings: string[];
  image_quality: string | null;
  recommended_action: string;
  model: string | null;
  analysed_at: string | null;
  disclaimer: string;
  body_part?: string;
  body_part_confidence?: number | null;
  condition?: string;
  condition_confidence?: number | null;
  model_metrics?: { condition_accuracy?: number; body_part_accuracy?: number };
}

interface Diagnostic {
  id: number;
  patient_id: number;
  patient_name: string;
  test_type: string;
  priority: string;
  status: string;
  result: string | null;
  requested_by: number | null;
  doctor_name: string | null;
  requested_at: string | null;
  completed_at: string | null;
  has_image: boolean;
  image_filename: string | null;
  image_uploaded_by: string | null;
  ai_report: AiReport | null;
  reviewed_by: string | null;
}

type DiagnosticsProps = {
  role?: string;
  email?: string;
};

const MAX_IMAGE_MB = 8;

function readAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1] ?? "");
    reader.onerror = () => reject(new Error("Could not read the selected file."));
    reader.readAsDataURL(file);
  });
}

function Diagnostics({ role, email = "" }: DiagnosticsProps) {
  const isNurse = role === "Nurse";
  const isDoctor = role === "Doctor";
  const [uploadingId, setUploadingId] = useState<number | null>(null);

  const [patients, setPatients] = useState<Patient[]>([]);
  const [doctors, setDoctors] = useState<DoctorOption[]>([]);
  const [diagnostics, setDiagnostics] = useState<Diagnostic[]>([]);

  const [selectedPatient, setSelectedPatient] = useState("");
  const [selectedDoctor, setSelectedDoctor] = useState("");
  const [testName, setTestName] = useState("");
  const [priority, setPriority] = useState("ROUTINE");

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  async function loadPatients() {
    const response = await fetch(`${API_BASE}/api/patients`);

    if (!response.ok) {
      throw new Error("Unable to load patients.");
    }

    const data = await response.json();
    setPatients(Array.isArray(data) ? data : []);
  }

  async function loadDoctors() {
    const response = await fetch(`${API_BASE}/api/doctors`);

    if (!response.ok) {
      throw new Error("Unable to load doctors.");
    }

    const data = await response.json();
    setDoctors(Array.isArray(data) ? data : []);
  }

  async function loadDiagnostics() {
    const response = await fetch(`${API_BASE}/api/diagnostics`);

    if (!response.ok) {
      throw new Error("Unable to load diagnostics.");
    }

    const data = await response.json();
    setDiagnostics(Array.isArray(data) ? data : []);
  }

  async function loadData() {
    try {
      setLoading(true);
      await Promise.all([
        loadPatients(),
        loadDoctors(),
        loadDiagnostics(),
      ]);
    } catch (error) {
      console.error(error);
      setMessage(
        error instanceof Error
          ? error.message
          : "Unable to load diagnostics."
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const load = async () => {
      await loadData();
    };

    load();
  }, []);

  async function createRequest() {
    if (!selectedPatient || !testName.trim()) {
      setMessage("Select a patient and enter a diagnostic test.");
      return;
    }

    try {
      setSaving(true);
      setMessage("");

      const response = await fetch(`${API_BASE}/api/diagnostics`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          patient_id: Number(selectedPatient),
          test_type: testName.trim(),
          priority,
          requested_by: selectedDoctor ? Number(selectedDoctor) : null,
        }),
      });

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(
          typeof data.detail === "string"
            ? data.detail
            : "Unable to create diagnostic request. Please check the details and try again."
        );
      }

      setMessage(data.message || "Diagnostic request created successfully.");
      setTestName("");
      setSelectedPatient("");
      setSelectedDoctor("");
      setPriority("ROUTINE");

      await loadDiagnostics();
    } catch (error) {
      console.error(error);
      setMessage(
        error instanceof Error
          ? error.message
          : "Unable to create diagnostic request."
      );
    } finally {
      setSaving(false);
    }
  }

  async function uploadImage(diagnosticId: number, file: File | undefined) {
    if (!file) return;
    if (!["image/png", "image/jpeg", "image/webp"].includes(file.type)) {
      setMessage("Upload a PNG, JPEG or WEBP image (export DICOM scans as PNG/JPEG first).");
      return;
    }
    if (file.size > MAX_IMAGE_MB * 1024 * 1024) {
      setMessage(`Image is too large. Maximum size is ${MAX_IMAGE_MB} MB.`);
      return;
    }

    try {
      setUploadingId(diagnosticId);
      setMessage("Uploading image and running AI analysis…");
      const image_base64 = await readAsBase64(file);

      const response = await fetch(`${API_BASE}/api/diagnostics/${diagnosticId}/image`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Staff-Email": email },
        body: JSON.stringify({ filename: file.name, image_base64 }),
      });
      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(
          typeof data.detail === "string" ? data.detail : "Unable to upload the image."
        );
      }

      setMessage(data.message || "Image analysed.");
      await loadDiagnostics();
    } catch (error) {
      console.error(error);
      setMessage(error instanceof Error ? error.message : "Unable to upload the image.");
    } finally {
      setUploadingId(null);
    }
  }

  async function updateStatus(
    diagnosticId: number,
    status: string
  ) {
    try {
      let result: string | null = null;

      const current = diagnostics.find((d) => d.id === diagnosticId);

      if (status === "COMPLETED" && current?.ai_report) {
        const note = window.prompt(
          "Confirm the final diagnosis (edit if you disagree with the AI reading):",
          current.ai_report.available && current.ai_report.problem ? current.ai_report.problem : ""
        );
        if (note === null) {
          return;
        }
        result = `Doctor reviewed: ${note.trim() || "no comment"}`;
      } else if (status === "COMPLETED") {
        const entered = window.prompt("Enter diagnostic result:");

        // Cancel on the prompt = do not complete the test.
        if (entered === null) {
          return;
        }

        result = entered.trim();
      }

      const params = new URLSearchParams({
        status,
      });

      if (result) {
        params.append("result", result);
      }

      const response = await fetch(
        `${API_BASE}/api/diagnostics/${diagnosticId}/status?${params.toString()}`,
        {
          method: "PATCH",
          headers: { "X-Staff-Email": email },
        }
      );

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(
          typeof data.detail === "string"
            ? data.detail
            : "Unable to update diagnostic."
        );
      }

      setMessage("Diagnostic status updated.");
      await loadDiagnostics();
    } catch (error) {
      console.error(error);
      setMessage(
        error instanceof Error
          ? error.message
          : "Unable to update diagnostic."
      );
    }
  }

  if (loading) {
    return (
      <div className="loading-state">
        Loading diagnostics...
      </div>
    );
  }

  const requested = diagnostics.filter(
    (item) => item.status === "REQUESTED"
  ).length;

  const inProgress = diagnostics.filter(
    (item) => item.status === "IN_PROGRESS"
  ).length;

  const completed = diagnostics.filter(
    (item) => item.status === "COMPLETED"
  ).length;

  return (
    <div className="diagnostics-page">

      <div className="module-heading">
        <div>
          <span className="eyebrow">
            DIAGNOSTIC OPERATIONS
          </span>

          <h3>Diagnostics</h3>

          <p>
            Manage diagnostic requests and coordinate
            test execution across the hospital.
          </p>
        </div>

        <div className="doctor-live-badge">
          <span className="status-dot" />
          {requested} Pending
        </div>
      </div>

      <div className="doctor-summary">

        <div className="summary-card">
          <span>Total Requests</span>
          <strong>{diagnostics.length}</strong>
        </div>

        <div className="summary-card">
          <span>Requested</span>
          <strong>{requested}</strong>
        </div>

        <div className="summary-card">
          <span>In Progress</span>
          <strong>{inProgress}</strong>
        </div>

        <div className="summary-card">
          <span>Completed</span>
          <strong>{completed}</strong>
        </div>

      </div>

      <section className="module-card">

        <div className="module-card-header">
          <div>
            <h4>New Diagnostic Request</h4>
            <span>
              Create a request for a patient
            </span>
          </div>
        </div>

        <div className="diagnostic-form">

          <select
            value={selectedPatient}
            onChange={(event) =>
              setSelectedPatient(event.target.value)
            }
          >
            <option value="">
              Select patient
            </option>

            {patients
              .filter((patient) => patient.status !== "DISCHARGED")
              .map((patient) => (
              <option
                key={patient.id}
                value={patient.id}
              >
                {patient.patient_code} — {patient.name}
              </option>
            ))}
          </select>

          <select
            value={selectedDoctor}
            onChange={(event) =>
              setSelectedDoctor(event.target.value)
            }
          >
            <option value="">
              Requesting doctor (optional)
            </option>

            {doctors.map((doctor) => (
              <option
                key={doctor.id}
                value={doctor.id}
              >
                {doctor.name} — {doctor.specialization}
              </option>
            ))}
          </select>

          <input
            type="text"
            placeholder="Diagnostic test (e.g. CBC, X-Ray, ECG)"
            value={testName}
            onChange={(event) =>
              setTestName(event.target.value)
            }
          />

          <select
            value={priority}
            onChange={(event) =>
              setPriority(event.target.value)
            }
          >
            <option value="ROUTINE">
              Routine
            </option>

            <option value="HIGH">
              High
            </option>

            <option value="URGENT">
              Urgent
            </option>

            <option value="CRITICAL">
              Critical
            </option>
          </select>

          <button
            className="availability-button"
            onClick={createRequest}
            disabled={saving}
          >
            {saving
              ? "Creating..."
              : "Create Request"}
          </button>

        </div>

        {message && (
          <div className="system-message">
            {message}
          </div>
        )}

      </section>

      <section className="module-card">

        <div className="module-card-header">
          <div>
            <h4>Diagnostic Requests</h4>
            <span>
              Current diagnostic workflow
            </span>
          </div>
        </div>

        {diagnostics.length === 0 ? (
          <div className="empty-state">
            No diagnostic requests yet.
          </div>
        ) : (
          <div className="diagnostic-list">

            {diagnostics.map((diagnostic) => (

              <div
                className="diagnostic-row"
                key={diagnostic.id}
              >

                <div className="diagnostic-main">

                  <strong>
                    {diagnostic.test_type}
                  </strong>

                  <span>
                    {diagnostic.patient_name}
                  </span>

                  <small>
                    Request #{diagnostic.id}
                    {diagnostic.doctor_name
                      ? ` · ${diagnostic.doctor_name}`
                      : ""}
                    {diagnostic.requested_at
                      ? ` · ${new Date(
                          diagnostic.requested_at
                        ).toLocaleString()}`
                      : ""}
                  </small>

                </div>

                <span
                  className={`availability-badge ${
                    diagnostic.priority.toLowerCase()
                  }`}
                >
                  {diagnostic.priority}
                </span>

                <span
                  className={`availability-badge ${
                    diagnostic.status.toLowerCase()
                  }`}
                >
                  {diagnostic.status}
                </span>

                <div className="diagnostic-actions">

                  {diagnostic.status === "REQUESTED" && (
                    <button
                      className="availability-button"
                      onClick={() =>
                        updateStatus(
                          diagnostic.id,
                          "IN_PROGRESS"
                        )
                      }
                    >
                      Start
                    </button>
                  )}

                  {(diagnostic.status === "REQUESTED" ||
                    diagnostic.status === "IN_PROGRESS" ||
                    diagnostic.status === "AWAITING_REVIEW") && !isNurse && (
                    <button
                      className="cancel-button"
                      onClick={() =>
                        updateStatus(
                          diagnostic.id,
                          "CANCELLED"
                        )
                      }
                    >
                      Cancel
                    </button>
                  )}

                  {((diagnostic.status === "IN_PROGRESS" && !isNurse) ||
                    (diagnostic.status === "AWAITING_REVIEW" && isDoctor)) && (
                    <button
                      className="availability-button"
                      onClick={() =>
                        updateStatus(
                          diagnostic.id,
                          "COMPLETED"
                        )
                      }
                    >
                      {diagnostic.status === "AWAITING_REVIEW" ? "Review & complete" : "Complete"}
                    </button>
                  )}

                  {diagnostic.status === "COMPLETED" &&
                    diagnostic.result && (
                      <span className="diagnostic-result">
                        {diagnostic.result}
                      </span>
                    )}

                </div>

                <div className="diagnostic-ai-wrap">
                  {isNurse &&
                    (diagnostic.status === "IN_PROGRESS" ||
                      diagnostic.status === "AWAITING_REVIEW") && (
                      <div className="ai-upload">
                        <label className="availability-button" style={{ cursor: "pointer" }}>
                          {uploadingId === diagnostic.id
                            ? "Analysing…"
                            : diagnostic.has_image
                            ? "Replace image"
                            : "Upload scan (X-Ray / CT / MRI)"}
                          <input
                            type="file"
                            accept="image/png,image/jpeg,image/webp"
                            hidden
                            disabled={uploadingId === diagnostic.id}
                            onChange={(event) => {
                              uploadImage(diagnostic.id, event.target.files?.[0]);
                              event.target.value = "";
                            }}
                          />
                        </label>
                        {diagnostic.image_filename && <small>{diagnostic.image_filename}</small>}
                      </div>
                    )}

                  {diagnostic.has_image && (isDoctor || isNurse) && (
                    <AiReportCard diagnostic={diagnostic} />
                  )}
                </div>

              </div>

            ))}

          </div>
        )}

      </section>

    </div>
  );
}


function AiReportCard({ diagnostic }: { diagnostic: Diagnostic }) {
  const report = diagnostic.ai_report;
  const imageUrl = `${API_BASE}/api/diagnostics/${diagnostic.id}/image`;

  if (!report) {
    return null;
  }

  const confidence = Math.round((report.confidence ?? 0) * 100);
  const level = confidence >= 75 ? "high" : confidence >= 50 ? "" : "low";

  return (
    <div className={`ai-report ${report.available ? "" : "ai-unavailable"}`}>
      <a href={imageUrl} target="_blank" rel="noreferrer" title="Open full image">
        <img
          src={imageUrl}
          alt={`${diagnostic.test_type} for ${diagnostic.patient_name}`}
        />
      </a>

      <div>
        <h5>
          AI imaging report
          {report.urgency && report.available && (
            <span className={`availability-badge ${report.urgency.toLowerCase()}`}>
              {report.urgency}
            </span>
          )}
        </h5>

        {report.available && report.body_part && report.body_part !== "unidentified" && (
          <>
            <h5>Detected in X-ray</h5>
            <p>
              <strong style={{ textTransform: "capitalize" }}>{report.body_part.replace(/_/g, " ")}</strong>
              {report.body_part_confidence != null && ` (${Math.round(report.body_part_confidence * 100)}% sure)`}
            </p>
          </>
        )}

        <h5>What happened</h5>
        <p className="ai-problem">{report.problem}</p>
        {report.available && report.condition && report.condition_confidence != null && (
          <p>
            {report.condition === "FRACTURE" ? "Fracture (break)" : "Normal"} —{" "}
            {Math.round(report.condition_confidence * 100)}% sure
          </p>
        )}

        {report.available && (
          <div className="ai-confidence">
            <span>Overall confidence <strong>{confidence}%</strong></span>
            <div className={`ai-confidence-bar ${level}`}>
              <span style={{ width: `${confidence}%` }} />
            </div>
          </div>
        )}

        <h5>Reason</h5>
        <p>{report.reason}</p>

        {report.findings.length > 0 && (
          <>
            <h5>Findings</h5>
            <ul>
              {report.findings.map((finding, index) => (
                <li key={index}>{finding}</li>
              ))}
            </ul>
          </>
        )}

        {report.recommended_action && (
          <>
            <h5>Suggested next step</h5>
            <p>{report.recommended_action}</p>
          </>
        )}

        <p className="ai-disclaimer">
          {report.disclaimer || "AI-assisted preliminary reading. A doctor must review it."}
          {report.available && " Confidence is the SVM's calibrated probability; it is only as reliable as its training data."}
          {diagnostic.reviewed_by && ` Reviewed by ${diagnostic.reviewed_by}.`}
        </p>
      </div>
    </div>
  );
}

export default Diagnostics;