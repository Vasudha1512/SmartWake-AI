"""CLI script to seed default challenge catalog into the SmartWake AI database.

Usage:
    python -m backend.app.database.seed_challenges

Safe to run multiple times. Idempotently inserts only missing templates
without creating duplicate records or altering existing data.
"""
import sys

from backend.app.database.session import SessionLocal
from backend.app.services.challenge_seed_service import seed_default_challenges


def run_seeding() -> int:
    """Execute challenge seeding against the active database."""
    print("=" * 65)
    print("SmartWake AI — Challenge Catalog Seeding")
    print("=" * 65)

    try:
        with SessionLocal() as db:
            result = seed_default_challenges(db)
            print(f"Catalog Defined:  {result.total_catalog} challenge templates")
            print(f"Records Inserted: {result.inserted}")
            print(f"Records Skipped:  {result.skipped} (already present in database)")
            print(f"Total in Database:{result.total_in_db} challenges")
            print("=" * 65)
            if result.inserted > 0:
                print(f"[SUCCESS] Successfully seeded {result.inserted} new challenge templates.")
            else:
                print("[SUCCESS] Database already fully seeded. No new records needed.")
            print("=" * 65)
            return 0
    except Exception as exc:
        print(f"\n[ERROR] Challenge seeding failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(run_seeding())
