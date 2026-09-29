from datetime import datetime
from app.database.base import Base



from sqlalchemy import Boolean, DateTime, Float, ForeignKey, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, deferred, mapped_column, relationship

class DiagnosticRequest(Base):
    __tablename__ = "diagnostic_requests"

    id: Mapped[int | None] = mapped_column(
        primary_key=True,
        autoincrement=True
    )

    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patients.id"),
        nullable=False
    )

    requested_by: Mapped[int | None] = mapped_column(
        ForeignKey("doctors.id"),
        nullable=True
    )

    test_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    priority: Mapped[str] = mapped_column(
        String(30),
        default="ROUTINE"
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="REQUESTED"
    )

    result: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True
    )

    requested_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )


    # ---- Diagnostic image + AI (computer-vision) report -----------------
    image_filename: Mapped[str | None] = mapped_column(String(200), nullable=True)
    image_mime: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # deferred: the image bytes are only loaded when explicitly accessed
    image_data: Mapped[bytes | None] = deferred(mapped_column(LargeBinary, nullable=True))
    image_uploaded_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    image_uploaded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    ai_available: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    ai_problem: Mapped[str | None] = mapped_column(String(300), nullable=True)
    ai_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_urgency: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ai_report: Mapped[str | None] = mapped_column(Text, nullable=True)  # full JSON report
    ai_model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    ai_analysed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)

    patient = relationship("Patient")
    doctor = relationship("Doctor")