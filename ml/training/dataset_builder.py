"""SQLAlchemy query pipeline to construct ML training datasets from SQLite.

CRITICAL PRODUCT & ML INTEGRITY RULES:
1. Queries historical ChallengeAttempt, WakeSession, Alarm, and SnoozeEvent records.
2. Safe cold-start handling: If the database contains 0 historical records, returns an
   empty dataset/DataFrame with all canonical columns intact, without raising exceptions.
3. No data leakage: All features for each historical row reflect strictly the state
   available prior to that attempt's outcome.
"""
from typing import Any, Dict, List, Optional
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from backend.app.models.challenge_attempt import ChallengeAttempt
from backend.app.models.wake_session import WakeSession
from ml.preprocessing.feature_engineering import extract_features_for_attempt
from ml.preprocessing.feature_schema import (
    ALL_DATASET_COLUMNS,
    FEATURE_COLUMNS,
    METADATA_COLUMNS,
    TARGET_COLUMNS,
    ChallengeFeatureRecord,
)


def build_challenge_feature_records(
    db: Session,
    user_id: Optional[int] = None,
) -> List[ChallengeFeatureRecord]:
    """Query historical attempts from database and extract canonical feature records.

    Args:
        db: Active SQLAlchemy database session.
        user_id: Optional user filter. If None, queries all users.

    Returns:
        List of ChallengeFeatureRecord instances, ordered chronologically.
    """
    stmt = (
        select(ChallengeAttempt)
        .join(WakeSession, ChallengeAttempt.wake_session_id == WakeSession.id)
        .options(joinedload(ChallengeAttempt.wake_session))
        .order_by(ChallengeAttempt.started_at.asc(), ChallengeAttempt.id.asc())
    )
    if user_id is not None:
        stmt = stmt.where(WakeSession.user_id == user_id)

    attempts = list(db.scalars(stmt).all())
    records: List[ChallengeFeatureRecord] = []

    for attempt in attempts:
        record = extract_features_for_attempt(db, attempt)
        records.append(record)

    return records


def build_challenge_feature_dataset(
    db: Session,
    user_id: Optional[int] = None,
    include_targets: bool = True,
    include_metadata: bool = True,
) -> List[Dict[str, Any]]:
    """Build a list-of-dicts dataset representation from historical records.

    Safe with empty database (returns [] without error).
    """
    records = build_challenge_feature_records(db=db, user_id=user_id)
    return [r.to_dict(include_targets=include_targets, include_metadata=include_metadata) for r in records]


def build_challenge_feature_dataframe(
    db: Session,
    user_id: Optional[int] = None,
    include_targets: bool = True,
    include_metadata: bool = True,
) -> pd.DataFrame:
    """Build a pandas DataFrame suitable for feature analysis or scikit-learn model training.

    Guarantees:
    - If 0 attempts exist in the database, returns an empty DataFrame with canonical column names.
    - Column ordering is strictly deterministic and adheres to ALL_DATASET_COLUMNS.
    - Safe against cold-start or empty-table states.
    """
    records = build_challenge_feature_records(db=db, user_id=user_id)

    # Determine desired columns based on inclusion flags
    columns: List[str] = []
    if include_metadata:
        columns.extend(METADATA_COLUMNS)
    columns.extend(FEATURE_COLUMNS)
    if include_targets:
        columns.extend(TARGET_COLUMNS)

    if not records:
        # Return empty DataFrame with exact column headers
        return pd.DataFrame(columns=columns)

    dicts = [r.to_dict(include_targets=include_targets, include_metadata=include_metadata) for r in records]
    df = pd.DataFrame(dicts)
    # Ensure exact column ordering
    existing_cols = [col for col in columns if col in df.columns]
    return df[existing_cols]
