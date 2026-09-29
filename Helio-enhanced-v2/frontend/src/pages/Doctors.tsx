import { useEffect, useState } from "react";

import { API_BASE } from "../config";

interface Doctor {
  id: number;
  name: string;
  specialization: string;
  department_id: number;
  staff_code?: string | null;
  years_experience?: number | null;
  is_available: boolean;
}

function Doctors() {
  const [doctors, setDoctors] = useState<Doctor[]>([]);
  const [loading, setLoading] = useState(true);
  const [updatingDoctorId, setUpdatingDoctorId] = useState<number | null>(
    null
  );
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  async function loadDoctors() {
    try {
      setLoading(true);
      setError("");

      const response = await fetch(`${API_BASE}/api/doctors`);

      if (!response.ok) {
        throw new Error("Failed to load doctors");
      }

      const data = await response.json();

      setDoctors(Array.isArray(data) ? data : []);
    } catch (error) {
      console.error(error);

      setError(
        error instanceof Error
          ? error.message
          : "Unable to load doctors."
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
  const load = async () => {
    await loadDoctors();
  };

  load();
}, []);

  async function toggleAvailability(doctor: Doctor) {
    try {
      setUpdatingDoctorId(doctor.id);
      setError("");
      setMessage("");

      const newAvailability = !doctor.is_available;

      const response = await fetch(
        `${API_BASE}/api/doctors/${doctor.id}/availability?is_available=${newAvailability}`,
        {
          method: "PATCH",
        }
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          data.detail || "Unable to update doctor availability."
        );
      }

      setDoctors((current) =>
        current.map((item) =>
          item.id === doctor.id
            ? {
                ...item,
                is_available: data.doctor.is_available,
              }
            : item
        )
      );

      setMessage(data.message || "Doctor availability updated.");
    } catch (error) {
      console.error(error);

      setError(
        error instanceof Error
          ? error.message
          : "Unable to update doctor availability."
      );
    } finally {
      setUpdatingDoctorId(null);
    }
  }

  if (loading) {
    return (
      <div className="loading-state">
        Loading doctors...
      </div>
    );
  }

  const available = doctors.filter(
    (doctor) => doctor.is_available
  ).length;

  const unavailable = doctors.length - available;

  return (
    <div className="doctors-page">

      {/* =========================
          PAGE HEADER
      ========================== */}

      <div className="module-heading">
        <div>
          <span className="eyebrow">CLINICAL STAFF</span>

          <h3>Doctors</h3>

          <p>
            Monitor doctor availability for appointment and
            patient workflow coordination.
          </p>
        </div>

        <div className="doctor-live-badge">
          <span className="status-dot" />
          {available} Available
        </div>
      </div>

      {/* =========================
          ERROR / SUCCESS MESSAGE
      ========================== */}

      {error && (
        <div className="system-message error-message">
          {error}
        </div>
      )}

      {message && !error && (
        <div className="system-message">
          {message}
        </div>
      )}

      {/* =========================
          SUMMARY
      ========================== */}

      <div className="doctor-summary">

        <div className="summary-card">
          <span>Total Doctors</span>
          <strong>{doctors.length}</strong>
        </div>

        <div className="summary-card">
          <span>Available</span>
          <strong>{available}</strong>
        </div>

        <div className="summary-card">
          <span>Unavailable</span>
          <strong>{unavailable}</strong>
        </div>

      </div>

      {/* =========================
          DOCTOR AVAILABILITY
      ========================== */}

      <section className="module-card">

        <div className="module-card-header">

          <div>
            <h4>Doctor Availability</h4>

            <span>
              Current availability status
            </span>
          </div>

        </div>

        <div className="doctor-grid">

          {doctors.map((doctor) => {

            const isUpdating =
              updatingDoctorId === doctor.id;

            return (
              <div
                className="doctor-card"
                key={doctor.id}
              >

                {/* TOP */}

                <div className="doctor-card-top">

                  <div className="doctor-avatar">
                    {doctor.name
                      .replace("Dr. ", "")
                      .charAt(0)
                      .toUpperCase()}
                  </div>

                  <span
                    className={`availability-badge ${
                      doctor.is_available
                        ? "available"
                        : "unavailable"
                    }`}
                  >
                    {doctor.is_available
                      ? "AVAILABLE"
                      : "UNAVAILABLE"}
                  </span>

                </div>

                {/* DOCTOR INFO */}

                <h4>{doctor.name}</h4>

                <p>{doctor.specialization}</p>

                {doctor.years_experience != null && (
                  <p>
                    {doctor.staff_code ? `${doctor.staff_code} · ` : ""}
                    {doctor.years_experience} yrs experience
                  </p>
                )}

                <div className="doctor-card-footer">

                  <span>
                    Department #{doctor.department_id}
                  </span>

                  <button
                    className="availability-button"
                    onClick={() =>
                      toggleAvailability(doctor)
                    }
                    disabled={isUpdating}
                  >
                    {isUpdating
                      ? "Updating..."
                      : doctor.is_available
                      ? "Set Unavailable"
                      : "Set Available"}
                  </button>

                </div>

              </div>
            );
          })}

        </div>

      </section>

    </div>
  );
}

export default Doctors;