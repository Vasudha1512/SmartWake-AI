"""SQLAlchemy database engine and session factory configuration."""
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from backend.app.core.config import settings

# SQLite requires 'check_same_thread': False when handling multi-threaded FastAPI requests
connect_args = (
    {"check_same_thread": False}
    if settings.DATABASE_URL.startswith("sqlite")
    else {}
)

# SQLAlchemy database engine
engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    echo=False,  # Set to True for verbose SQL query logging during development
)

# Session factory bound to the engine
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a transactional SQLAlchemy database session per request.

    Guarantees the session is properly closed after request processing completes.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
