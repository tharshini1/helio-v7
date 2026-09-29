import { useEffect, useState } from "react";

import { API_BASE } from "../config";

interface Stats {
  total_patients: number;
  critical_patients: number;
  available_beds: number;
  total_beds: number;
  available_doctors: number;
  total_doctors: number;
  available_nurses: number;
  total_nurses: number;
  pending_approvals: number;
}

function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {

  async function loadDashboard() {
    try {
      const statsResponse = await fetch(`${API_BASE}/api/stats`);

      if (!statsResponse.ok) {
        throw new Error("Failed to load dashboard");
      }

      const statsData = await statsResponse.json();

      setStats(statsData);
    } catch (error) {
      console.error("Dashboard error:", error);
    } finally {
      setLoading(false);
    }
  }
  loadDashboard();
  }, []);

  if (loading) {
    return (
      <div className="loading-state">
        Loading hospital operations...
      </div>
    );
  }

  return (
    <div className="dashboard">
      {/* OVERVIEW */}

      <div className="dashboard-heading">
        <div>
          <span className="eyebrow">LIVE OPERATIONS</span>
          <h3>Hospital Overview</h3>
          <p>
            Real-time coordination of hospital resources and workflows.
          </p>
        </div>

        <div className="live-indicator">
          <span className="status-dot" />
          Live
        </div>
      </div>

      {/* STAT CARDS */}

      <div className="stats-grid">
        <StatCard
          title="Total Patients"
          value={stats?.total_patients ?? 0}
          subtitle="Currently registered"
          icon="♙"
        />

        <StatCard
          title="Critical Patients"
          value={stats?.critical_patients ?? 0}
          subtitle="Require priority handling"
          icon="!"
          danger
        />

        <StatCard
          title="Available Beds"
          value={stats?.available_beds ?? 0}
          subtitle={`of ${stats?.total_beds ?? 0} total beds`}
          icon="▦"
        />

        <StatCard
          title="Available Doctors"
          value={stats?.available_doctors ?? 0}
          subtitle={`of ${stats?.total_doctors ?? 0} doctors`}
          icon="◉"
        />

        <StatCard
          title="Available Nurses"
          value={stats?.available_nurses ?? 0}
          subtitle={`of ${stats?.total_nurses ?? 0} nurses`}
          icon="+"
        />

        <StatCard
          title="Pending Approvals"
          value={stats?.pending_approvals ?? 0}
          subtitle="Human decisions required"
          icon="✓"
          warning
        />
      </div>

      {/* LOWER SECTION */}

      <div className="dashboard-columns">
        {/* RESOURCE STATUS */}

        <section className="dashboard-card">
          <div className="card-header">
            <div>
              <h4>Resource Status</h4>
              <span>Current hospital capacity</span>
            </div>
          </div>

          <ResourceBar
            label="Beds"
            available={stats?.available_beds ?? 0}
            total={stats?.total_beds ?? 0}
          />

          <ResourceBar
            label="Doctors"
            available={stats?.available_doctors ?? 0}
            total={stats?.total_doctors ?? 0}
          />

          <ResourceBar
            label="Nurses"
            available={stats?.available_nurses ?? 0}
            total={stats?.total_nurses ?? 0}
          />

          <div className="workflow-box">
            <div className="workflow-icon">✦</div>

            <div>
              <strong>Multi-Agent Coordination</strong>
              <span>
                Appointment, resource and workflow agents are connected.
              </span>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

function StatCard({
  title,
  value,
  subtitle,
  icon,
  danger,
  warning,
}: {
  title: string;
  value: number;
  subtitle: string;
  icon: string;
  danger?: boolean;
  warning?: boolean;
}) {
  return (
    <div className="stat-card">
      <div
        className={`stat-icon ${
          danger ? "danger" : warning ? "warning" : ""
        }`}
      >
        {icon}
      </div>

      <div className="stat-content">
        <span>{title}</span>
        <strong>{value}</strong>
        <small>{subtitle}</small>
      </div>
    </div>
  );
}

function ResourceBar({
  label,
  available,
  total,
}: {
  label: string;
  available: number;
  total: number;
}) {
  const percentage =
    total > 0 ? Math.round((available / total) * 100) : 0;

  return (
    <div className="resource-row">
      <div className="resource-label">
        <strong>{label}</strong>
        <span>
          {available} available / {total}
        </span>
      </div>

      <div className="resource-track">
        <div
          className="resource-fill"
          style={{ width: `${percentage}%` }}
        />
      </div>

      <span className="resource-percent">
        {percentage}%
      </span>
    </div>
  );
}

export default Dashboard;