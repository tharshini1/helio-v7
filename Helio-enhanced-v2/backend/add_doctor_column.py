from sqlalchemy import text

from app.database.connection import engine


def migrate():
    with engine.begin() as connection:

        connection.execute(
            text(
                """
                ALTER TABLE patients
                ADD COLUMN doctor_id INTEGER
                """
            )
        )

    print("doctor_id column added successfully.")


if __name__ == "__main__":
    migrate()