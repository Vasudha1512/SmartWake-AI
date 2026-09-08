"""Database package for SmartWake AI.

Exports the engine, session factory, declarative base, session dependency,
and database initialization routine.
"""
from backend.app.database.base import Base
from backend.app.database.session import engine, SessionLocal, get_db
from backend.app.database.init_db import init_db

__all__ = ["Base", "engine", "SessionLocal", "get_db", "init_db"]
