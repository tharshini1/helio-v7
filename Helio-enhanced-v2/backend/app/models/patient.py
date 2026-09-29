from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import ForeignKey
from app.database.base import Base


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    patient_code: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    age: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    gender: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    symptoms: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    heart_rate: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    spo2: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    temperature: Mapped[float | None] = mapped_column(
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        default="WAITING",
        nullable=False,
    )
    doctor_id: Mapped[int | None] = mapped_column(
    ForeignKey("doctors.id"),
    nullable=True
    )

    # Self-registered patient accounts (nullable: dataset patients have none)
    email: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
        index=True,
    )

    phone: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        index=True,
    )

    password_hash: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )
