from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Bed(Base):
    __tablename__ = "beds"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    bed_code: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        nullable=False,
    )

    ward_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    department_id: Mapped[int] = mapped_column(
        ForeignKey("departments.id"),
        nullable=False,
    )

    is_occupied: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    patient_id: Mapped[int | None] = mapped_column(
        ForeignKey("patients.id"),
        nullable=True,
    )

    department = relationship(
        "Department",
        back_populates="beds",
    )