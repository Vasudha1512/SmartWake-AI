"""SQLAlchemy Declarative Base definition."""

try:
    from sqlalchemy.orm import DeclarativeBase

    class Base(DeclarativeBase):
        """Base class for all SQLAlchemy ORM models in SmartWake AI."""
        pass

except ImportError:
    from sqlalchemy.ext.declarative import declarative_base

    Base = declarative_base()
