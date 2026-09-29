from app.database.base import Base
from app.database.connection import engine

# Import all models so SQLAlchemy knows about them.
from app.models import (
    Department,
    Doctor,
    Patient,
    Bed,
)


def init_database():
    Base.metadata.create_all(bind=engine)