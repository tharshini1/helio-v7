from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class EmergencyAlert(Base):
    """A nurse-raised emergency page sent to the doctors on call for a specialty."""

    __tablename__ = "emergency_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    emergency_type: Mapped[str] = mapped_column(String(50), nullable=False)
    emergency_label: Mapped[str] = mapped_column(String(120), nullable=False)
    required_specialty: Mapped[str] = mapped_column(String(100), nullable=False)

    patient_label: Mapped[str] = mapped_column(String(150), nullable=False)
    location: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # JSON lists: [{"id": 1, "name": "Dr. X", "specialization": "..."}]
    paged_doctors: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    # ACTIVE -> ACKNOWLEDGED (a doctor is responding) or CANCELLED (false alarm)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE", index=True)

    raised_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    acknowledged_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
