"""Database initialization routines."""
from backend.app.database.session import engine
from backend.app.database.base import Base


def init_db() -> None:
    """Initialize database tables.

    Creates all tables registered on the Declarative Base metadata
    if they do not already exist in the SQLite database.
    Safe to run multiple times without deleting existing tables or data.
    """
    import backend.app.models  # Ensures all ORM models are registered with Base.metadata
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    init_db()
    print("Database initialization complete. All tables created.")
