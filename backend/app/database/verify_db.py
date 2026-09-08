"""Database verification script for SmartWake AI.

Verifies:
1. All seven expected SQLite tables exist.
2. A SQLAlchemy session can be opened and queried successfully.
3. No sample data has been inadvertently inserted.
"""
import sys
from typing import Dict, List, Set
from sqlalchemy import inspect, text

from backend.app.database.session import engine, SessionLocal

EXPECTED_TABLES: Set[str] = {
    "users",
    "alarms",
    "wake_sessions",
    "snooze_events",
    "challenges",
    "challenge_attempts",
    "ml_adaptive_logs",
}


def verify_database() -> bool:
    """Inspect the database and verify tables, session connectivity, and empty data state."""
    print("=" * 60)
    print("SmartWake AI — Database Verification")
    print("=" * 60)

    # 1. Inspect actual SQLite table names
    inspector = inspect(engine)
    actual_tables: Set[str] = set(inspector.get_table_names())

    print(f"\n[1] Table Verification:")
    print(f"    Expected ({len(EXPECTED_TABLES)}): {sorted(list(EXPECTED_TABLES))}")
    print(f"    Found    ({len(actual_tables)}): {sorted(list(actual_tables))}")

    missing_tables = EXPECTED_TABLES - actual_tables
    extra_tables = actual_tables - EXPECTED_TABLES

    if missing_tables:
        print(f"\n[ERROR] Missing expected tables: {missing_tables}")
        return False

    print("    [SUCCESS] All 7 expected tables are present in the SQLite database.")

    # 2. Test SQLAlchemy Session connectivity
    print(f"\n[2] Session Connectivity Test:")
    try:
        with SessionLocal() as session:
            result = session.execute(text("SELECT 1")).scalar()
            if result == 1:
                print("    [SUCCESS] SQLAlchemy session opened and query executed successfully.")
            else:
                print(f"    [ERROR] Unexpected query result from session: {result}")
                return False
    except Exception as e:
        print(f"    [ERROR] Failed to establish database session: {e}")
        return False

    # 3. Verify that no sample data was inserted (clean state)
    print(f"\n[3] Data State Verification (Zero Sample Data Check):")
    total_records = 0
    with SessionLocal() as session:
        for table_name in sorted(list(EXPECTED_TABLES)):
            count = session.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
            print(f"    - Table '{table_name}': {count} records")
            total_records += count

    if total_records == 0:
        print("    [SUCCESS] Verified: Exactly 0 records found across all tables (no sample data inserted).")
    else:
        print(f"    [WARNING] Found {total_records} existing records in the database.")

    print("\n" + "=" * 60)
    print("DATABASE INFRASTRUCTURE & TABLES VERIFIED SUCCESSFULLY")
    print("=" * 60)
    return True


if __name__ == "__main__":
    success = verify_database()
    sys.exit(0 if success else 1)
