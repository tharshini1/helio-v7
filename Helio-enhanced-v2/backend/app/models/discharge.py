from datetime import datetime

from app.database.base import Base

from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship


class DischargeRequest(Base):
    __tablename__ = "discharge_requests"

    id: Mapped[int | None] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patients.id"),
        nullable=False,
    )

    doctor_id: Mapped[int | None] = mapped_column(
        ForeignKey("doctors.id"),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="PENDING",
    )

    reason: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    instructions: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    admission_date: Mapped[str | None] = mapped_column(String(30), nullable=True)
    discharge_date: Mapped[str | None] = mapped_column(String(30), nullable=True)
    diagnosis: Mapped[str | None] = mapped_column(String(500), nullable=True)
    medication: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)

    patient = relationship("Patient")
    doctor = relationship("Doctor")