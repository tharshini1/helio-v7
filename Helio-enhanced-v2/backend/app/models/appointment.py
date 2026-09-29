from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[int | None] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patients.id"),
        nullable=False,
    )

    doctor_id: Mapped[int] = mapped_column(
        ForeignKey("doctors.id"),
        nullable=False,
    )

    appointment_date: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    appointment_time: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )

    reason: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="SCHEDULED",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    visited_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    visited_by: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    # Post-visit bed decision (None = not decided yet)
    bed_needed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    bed_decision_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    bed_decision_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    bed_code: Mapped[str | None] = mapped_column(String(20), nullable=True)

    patient = relationship("Patient")
    doctor = relationship("Doctor")
