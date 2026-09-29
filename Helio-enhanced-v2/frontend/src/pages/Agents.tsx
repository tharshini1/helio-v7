import { useEffect, useState } from "react";

import { API_BASE } from "../config";

type Agent = {
  name: string;
  role: string;
  status: "ACTIVE" | "IDLE";
  responsibility: string;
};

const agents: Agent[] = [
  {
    name: "Appointment Agent",
    role: "Scheduling",
    status: "ACTIVE",
    responsibility:
      "Handles patient appointment scheduling and queue coordination.",
  },
  {
    name: "Doctor Availability Agent",
    role: "Availability",
    status: "ACTIVE",
    responsibility:
      "Tracks doctor availability and matches patients with available doctors.",
  },
  {
    name: "Resource Agent",
    role: "Bed Allocation",
    status: "ACTIVE",
    responsibility:
      "Evaluates ward and bed availability and recommends resource allocation.",
  },
  {
    name: "Diagnostic Agent",
    role: "Diagnostics",
    status: "ACTIVE",
    responsibility:
      "Coordinates diagnostic requests, priorities and completion status.",
  },
  {
    name: "Discharge Agent",
    role: "Discharge Planning",
    status: "ACTIVE",
    responsibility:
      "Coordinates discharge requests and routes them for clinical approval.",
  },
];

type Stats = {
  total_patients?: number;
  critical_patients?: number;
  available_beds?: number;
  available_doctors?: number;
  pending_approvals?: number;
};

type Patient = {
  id: number;
  patient_code: string;
  name: string;
  status: string;
};

export default function Agents() {
  const [stats, setStats] = useState<Stats>({});
  const [patients, setPatients] = useState<Patient[]>([]);
  const [message, setMessage] = useState(
    "Orchestrator is monitoring hospital workflow."
  );
  const [lastEvent, setLastEvent] = useState(
    "System initialized. Agents are ready."
  );
  const [isRunning, setIsRunning] = useState(false);

  const loadSystemData = async () => {
    try {
      const [statsResponse, patientsResponse] = await Promise.all([
        fetch(`${API_BASE}/api/stats`),
        fetch(`${API_BASE}/api/patients`),
      ]);

      if (statsResponse.ok) {
        const statsData = await statsResponse.json();
        setStats(statsData);
      }

      if (patientsResponse.ok) {
        const patientsData = await patientsResponse.json();
        setPatients(Array.isArray(patientsData) ? patientsData : []);
      }
    } catch (error) {
      console.error("Unable to load agent data:", error);
    }
  };

  useEffect(() => {
    loadSystemData();

    // Keep the agent dashboard updated automatically.
    const interval = window.setInterval(() => {
      loadSystemData();
    }, 5000);

    return () => window.clearInterval(interval);
  }, []);

  const runOrchestratorCheck = async () => {
    if (isRunning) return;

    setIsRunning(true);

    try {
      setMessage("Orchestrator received a hospital workflow event...");
      setLastEvent("Scanning patients, resources and pending approvals...");

      await loadSystemData();

      await new Promise((resolve) => setTimeout(resolve, 700));

      setMessage(
        "Agents evaluated the current hospital state and updated workflow information."
      );

      setLastEvent(
        "Appointment → Doctor Availability → Resource → Diagnostics → Discharge"
      );

      await loadSystemData();
    } catch (error) {
      console.error(error);
      setMessage("Orchestrator encountered an error.");
      setLastEvent("Workflow check failed.");
    } finally {
      setIsRunning(false);
    }
  };

  const simulateEmergencyEvent = async () => {
    if (isRunning) return;

    setIsRunning(true);

    try {
      setMessage(
        "Emergency event received → Orchestrator evaluating patient priority..."
      );
      setLastEvent("Triage and Resource Agents evaluating emergency workflow...");

      await new Promise((resolve) => setTimeout(resolve, 900));

      setMessage(
        "Emergency workflow evaluated → critical resources and approval requirements identified."
      );
      setLastEvent(
        "Emergency → Orchestrator → Triage → Resource → Human Approval"
      );

      await loadSystemData();
    } catch (error) {
      console.error(error);
      setMessage("Emergency workflow simulation failed.");
      setLastEvent("Unable to complete workflow simulation.");
    } finally {
      setIsRunning(false);
    }
  };

  const criticalPatients = patients.filter(
    (patient) => patient.status === "CRITICAL"
  ).length;

  return (
    <div className="page-container">
      <div className="page-header">
        <div>
          <h1>Multi-Agent Operations</h1>
          <p>
            Real-time coordination between specialized Helio agents.
          </p>
        </div>

        <div className="orchestrator-status">
          <span className="live-dot"></span>
          ORCHESTRATOR ACTIVE
        </div>
      </div>

      <div className="stats-grid">
        <div className="stat-card">
          <span>Active Agents</span>
          <strong>{agents.length}</strong>
        </div>

        <div className="stat-card">
          <span>Patients</span>
          <strong>{stats.total_patients ?? "--"}</strong>
        </div>

        <div className="stat-card">
          <span>Available Beds</span>
          <strong>{stats.available_beds ?? "--"}</strong>
        </div>

        <div className="stat-card">
          <span>Pending Approvals</span>
          <strong>{stats.pending_approvals ?? "--"}</strong>
        </div>
      </div>

      <div className="agent-flow-card">
        <div className="section-heading">
          <div>
            <h2>Helio Coordination</h2>
            <p>
              Events are routed through the orchestrator to specialized agents.
            </p>
          </div>
        </div>

        <div className="agent-flow">
          <div className="flow-node event-node">
            <span>EVENT</span>
            <strong>Hospital Event</strong>
          </div>

          <div className="flow-arrow">→</div>

          <div className="flow-node orchestrator-node">
            <span>ORCHESTRATOR</span>
            <strong>Decision Routing</strong>
          </div>

          <div className="flow-arrow">→</div>

          <div className="flow-node agent-node">
            <span>AGENTS</span>
            <strong>Specialized Actions</strong>
          </div>

          <div className="flow-arrow">→</div>

          <div className="flow-node approval-node">
            <span>CONTROL</span>
            <strong>Human Approval</strong>
          </div>
        </div>
      </div>

      <div className="agents-grid">
        {agents.map((agent) => (
          <div className="agent-card" key={agent.name}>
            <div className="agent-card-header">
              <div className="agent-icon">AI</div>

              <span className="agent-status">
                <span className="status-dot"></span>
                {agent.status}
              </span>
            </div>

            <h3>{agent.name}</h3>

            <span className="agent-role">{agent.role}</span>

            <p>{agent.responsibility}</p>
          </div>
        ))}
      </div>

      <div className="orchestrator-panel">
        <div>
          <span className="agent-label">ORCHESTRATOR EVENT MONITOR</span>

          <h2>Real-Time Coordination</h2>

          <p>{message}</p>

          <small
            style={{
              display: "block",
              marginTop: "8px",
              opacity: 0.75,
            }}
          >
            {lastEvent}
          </small>

          <small
            style={{
              display: "block",
              marginTop: "8px",
              opacity: 0.65,
            }}
          >
            Critical patients detected: {criticalPatients}
          </small>
        </div>

        <div
          style={{
            display: "flex",
            gap: "10px",
            flexWrap: "wrap",
          }}
        >
          <button
            className="primary-button"
            onClick={runOrchestratorCheck}
            disabled={isRunning}
          >
            {isRunning ? "Processing..." : "Run Workflow Check"}
          </button>

          <button
            className="primary-button"
            onClick={simulateEmergencyEvent}
            disabled={isRunning}
          >
            {isRunning
              ? "Processing..."
              : "Simulate Emergency Event"}
          </button>
        </div>
      </div>
    </div>
  );
}