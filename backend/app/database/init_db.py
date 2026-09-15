"""Database initialization routines."""
from backend.app.database.session import engine
from backend.app.database.base import Base


def init_db() -> None:
    """Initialize database tables and run lightweight schema migrations.

    Creates all tables registered on the Declarative Base metadata
    if they do not already exist in the SQLite database.
    Safely upgrades existing tables if newly added User columns
    (hashed_password, is_active) are missing, without altering existing
    records or creating fake users.
    """
    import backend.app.models  # Ensures all ORM models are registered with Base.metadata
    Base.metadata.create_all(bind=engine)

    # SQLite migration: safely add missing authentication columns to existing users table
    with engine.connect() as conn:
        cursor = conn.exec_driver_sql("PRAGMA table_info(users)")
        existing_columns = {row[1] for row in cursor.fetchall()}
        if existing_columns:
            if "hashed_password" not in existing_columns:
                conn.exec_driver_sql("ALTER TABLE users ADD COLUMN hashed_password VARCHAR(255)")
            if "is_active" not in existing_columns:
                conn.exec_driver_sql("ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1")
            conn.commit()



if __name__ == "__main__":
    init_db()
    print("Database initialization complete. All tables created.")
