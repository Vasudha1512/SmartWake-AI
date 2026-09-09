"""Feature engineering and historical telemetry aggregation for ML adaptive intelligence.

CRITICAL DATA-LEAKAGE PREVENTION RULE:
When computing features for an attempt or session, only historical data generated PRIOR to
the reference timestamp (attempt.started_at or decision_timestamp) is queried and aggregated.
The current attempt's outcome fields (is_successful, completed_at, duration_seconds,
verification_score, verification_result, failure_reason) are NEVER referenced during feature
extraction.
"""
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.datetime_utils import ensure_utc, diff_seconds, now_utc
from backend.app.models.alarm import Alarm
from backend.app.models.challenge_attempt import ChallengeAttempt
from backend.app.models.snooze_event import SnoozeEvent
from backend.app.models.wake_session import WakeSession
from ml.preprocessing.feature_schema import ChallengeFeatureRecord


def _safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Safe division returning default if denominator is zero or near-zero."""
    if denominator == 0 or denominator is None or numerator is None:
        return default
    return round(float(numerator) / float(denominator), 4)


def extract_features_for_session_context(
    db: Session,
    wake_session: WakeSession,
    challenge_type: str,
    difficulty_preference: str = "adaptive",
    ref_time: Optional[datetime] = None,
    current_attempt_id: Optional[int] = None,
    current_attempt_number: int = 1,
) -> ChallengeFeatureRecord:
    """Extract canonical feature record for a wake session and challenge context.

    This function computes all historical features strictly available BEFORE the challenge
    outcome occurs. Used at both challenge-generation runtime (prediction) and dataset
    construction (offline training).

    Args:
        db: SQLAlchemy database session.
        wake_session: The current WakeSession instance.
        challenge_type: The user-selected canonical challenge type.
        difficulty_preference: Baseline user preference ('adaptive', 'easy', 'medium', 'hard').
        ref_time: Reference timestamp representing the exact moment before execution. Defaults to now_utc().
        current_attempt_id: Optional ID of the attempt if building training data for an existing attempt.
        current_attempt_number: Sequence number of the attempt (1 for initial, 2+ for retries).

    Returns:
        ChallengeFeatureRecord populated with historical and pre-attempt context.
    """
    user_id = wake_session.user_id
    alarm_id = wake_session.alarm_id
    if ref_time is None:
        ref_time = now_utc()

    # 1. Fetch prior wake sessions for this user strictly before the current session's scheduled time
    # (or strictly prior session ID if scheduled_time is identical).
    # We only consider sessions that reached a terminal status ("completed", "abandoned").
    prior_sessions_query = (
        select(WakeSession)
        .where(
            WakeSession.user_id == user_id,
            WakeSession.id != wake_session.id,
            WakeSession.scheduled_time <= wake_session.scheduled_time,
            WakeSession.status.in_(["completed", "abandoned"]),
        )
        .order_by(WakeSession.scheduled_time.desc(), WakeSession.id.desc())
    )
    prior_sessions = list(db.scalars(prior_sessions_query).all())

    user_total_wake_sessions = len(prior_sessions)
    user_successful_wake_sessions = sum(1 for s in prior_sessions if s.status == "completed")
    user_failed_wake_sessions = sum(1 for s in prior_sessions if s.status == "abandoned")
    user_historical_success_rate = _safe_divide(user_successful_wake_sessions, user_total_wake_sessions, 0.0)

    # Snooze aggregates across prior wake sessions
    prior_snooze_counts = [s.total_snooze_count for s in prior_sessions if s.total_snooze_count is not None]
    user_total_snooze_count = sum(prior_snooze_counts)
    user_avg_snooze_count = (
        _safe_divide(user_total_snooze_count, len(prior_snooze_counts), 0.0) if prior_snooze_counts else 0.0
    )
    user_recent_snooze_count = prior_sessions[0].total_snooze_count if prior_sessions else 0

    # 2. Fetch prior challenge attempts for this user across prior sessions
    # plus any prior attempts within the current session that completed before ref_time
    prior_session_ids = [s.id for s in prior_sessions]

    prior_attempts: List[ChallengeAttempt] = []
    if prior_session_ids:
        prior_attempts_query = (
            select(ChallengeAttempt)
            .where(
                ChallengeAttempt.wake_session_id.in_(prior_session_ids),
                ChallengeAttempt.completed_at.isnot(None),
            )
            .order_by(ChallengeAttempt.completed_at.desc())
        )
        prior_attempts.extend(list(db.scalars(prior_attempts_query).all()))

    # Intra-session prior attempts (e.g. if this is attempt #2, attempt #1 is historical)
    current_session_prior_attempts_query = (
        select(ChallengeAttempt)
        .where(
            ChallengeAttempt.wake_session_id == wake_session.id,
            ChallengeAttempt.attempt_number < current_attempt_number,
            ChallengeAttempt.completed_at.isnot(None),
        )
        .order_by(ChallengeAttempt.attempt_number.asc())
    )
    current_session_prior_attempts = list(db.scalars(current_session_prior_attempts_query).all())
    prior_attempts.extend(current_session_prior_attempts)

    # Sort all prior attempts by completion timestamp descending
    prior_attempts.sort(
        key=lambda a: ensure_utc(a.completed_at) if a.completed_at else ensure_utc(a.created_at),
        reverse=True,
    )

    # Overall attempt & completion time metrics across all challenge types
    user_avg_attempts_per_session = (
        _safe_divide(len(prior_attempts), user_total_wake_sessions, 0.0) if user_total_wake_sessions > 0 else 0.0
    )

    completed_durations = [
        a.duration_seconds
        for a in prior_attempts
        if a.is_successful is True and a.duration_seconds is not None and a.duration_seconds > 0
    ]
    user_avg_completion_time_seconds = (
        _safe_divide(sum(completed_durations), len(completed_durations), 0.0) if completed_durations else 0.0
    )

    # Recent challenge success rate (rolling last 5 attempts)
    recent_5_attempts = prior_attempts[:5]
    recent_successful = sum(1 for a in recent_5_attempts if a.is_successful is True)
    user_recent_challenge_success_rate = (
        _safe_divide(recent_successful, len(recent_5_attempts), 0.0) if recent_5_attempts else 0.0
    )

    # 3. Challenge-specific historical metrics (strictly for challenge_type)
    type_attempts = [a for a in prior_attempts if a.challenge_type == challenge_type]
    challenge_type_total_attempts = len(type_attempts)
    challenge_type_successful_attempts = sum(1 for a in type_attempts if a.is_successful is True)
    challenge_type_success_rate = _safe_divide(
        challenge_type_successful_attempts, challenge_type_total_attempts, 0.0
    )

    type_durations = [
        a.duration_seconds
        for a in type_attempts
        if a.is_successful is True and a.duration_seconds is not None and a.duration_seconds > 0
    ]
    challenge_type_avg_completion_time = (
        _safe_divide(sum(type_durations), len(type_durations), 0.0) if type_durations else 0.0
    )

    # Sessions where this challenge type was used
    type_session_ids = set(a.wake_session_id for a in type_attempts)
    challenge_type_avg_attempts_per_session = (
        _safe_divide(challenge_type_total_attempts, len(type_session_ids), 0.0) if type_session_ids else 0.0
    )

    # Difficulty breakdown for this challenge type
    easy_type_attempts = [a for a in type_attempts if a.difficulty_level == "easy"]
    challenge_type_easy_attempts = len(easy_type_attempts)
    challenge_type_easy_success_rate = _safe_divide(
        sum(1 for a in easy_type_attempts if a.is_successful is True),
        challenge_type_easy_attempts,
        0.0,
    )

    medium_type_attempts = [a for a in type_attempts if a.difficulty_level == "medium"]
    challenge_type_medium_attempts = len(medium_type_attempts)
    challenge_type_medium_success_rate = _safe_divide(
        sum(1 for a in medium_type_attempts if a.is_successful is True),
        challenge_type_medium_attempts,
        0.0,
    )

    hard_type_attempts = [a for a in type_attempts if a.difficulty_level == "hard"]
    challenge_type_hard_attempts = len(hard_type_attempts)
    challenge_type_hard_success_rate = _safe_divide(
        sum(1 for a in hard_type_attempts if a.is_successful is True),
        challenge_type_hard_attempts,
        0.0,
    )

    # 4. SNOOZE_HISTORY in current session strictly BEFORE ref_time
    # Snooze events recorded up to ref_time
    snoozes_query = (
        select(SnoozeEvent)
        .where(
            SnoozeEvent.wake_session_id == wake_session.id,
            SnoozeEvent.snoozed_at <= ref_time,
        )
        .order_by(SnoozeEvent.snooze_number.asc())
    )
    current_session_snoozes = list(db.scalars(snoozes_query).all())
    current_session_snooze_count = len(current_session_snoozes)
    current_session_snooze_duration_minutes = sum(s.snooze_duration_minutes for s in current_session_snoozes)

    # Wake delay: seconds from initial_ring_time to ref_time
    current_session_wake_delay_seconds = max(0.0, diff_seconds(ref_time, wake_session.initial_ring_time))

    # 5. ALARM_CONTEXT
    scheduled_dt = ensure_utc(wake_session.scheduled_time)
    alarm_scheduled_hour = scheduled_dt.hour
    alarm_scheduled_minute = scheduled_dt.minute
    alarm_day_of_week = scheduled_dt.weekday()  # 0=Monday, 6=Sunday
    alarm_is_weekend = 1 if alarm_day_of_week >= 5 else 0

    # Historical average snoozes for alarms scheduled within ±1 hour
    target_hour = alarm_scheduled_hour
    similar_hour_sessions = [
        s for s in prior_sessions
        if abs(ensure_utc(s.scheduled_time).hour - target_hour) <= 1
    ]
    historical_snooze_avg_around_alarm_time = (
        _safe_divide(
            sum(s.total_snooze_count for s in similar_hour_sessions),
            len(similar_hour_sessions),
            0.0,
        )
        if similar_hour_sessions
        else 0.0
    )

    # 6. CURRENT_CONTEXT
    is_adaptive_preference = 1 if difficulty_preference == "adaptive" else 0

    # Format timestamp
    ref_iso = ensure_utc(ref_time).isoformat()

    return ChallengeFeatureRecord(
        user_id=user_id,
        wake_session_id=wake_session.id,
        challenge_attempt_id=current_attempt_id,
        alarm_id=alarm_id,
        timestamp=ref_iso,
        # User history
        user_total_wake_sessions=user_total_wake_sessions,
        user_successful_wake_sessions=user_successful_wake_sessions,
        user_failed_wake_sessions=user_failed_wake_sessions,
        user_historical_success_rate=user_historical_success_rate,
        user_avg_completion_time_seconds=user_avg_completion_time_seconds,
        user_avg_attempts_per_session=user_avg_attempts_per_session,
        user_avg_snooze_count=user_avg_snooze_count,
        user_total_snooze_count=user_total_snooze_count,
        user_recent_snooze_count=user_recent_snooze_count,
        user_recent_challenge_success_rate=user_recent_challenge_success_rate,
        # Challenge history
        challenge_type_total_attempts=challenge_type_total_attempts,
        challenge_type_successful_attempts=challenge_type_successful_attempts,
        challenge_type_success_rate=challenge_type_success_rate,
        challenge_type_avg_completion_time=challenge_type_avg_completion_time,
        challenge_type_avg_attempts_per_session=challenge_type_avg_attempts_per_session,
        challenge_type_easy_attempts=challenge_type_easy_attempts,
        challenge_type_easy_success_rate=challenge_type_easy_success_rate,
        challenge_type_medium_attempts=challenge_type_medium_attempts,
        challenge_type_medium_success_rate=challenge_type_medium_success_rate,
        challenge_type_hard_attempts=challenge_type_hard_attempts,
        challenge_type_hard_success_rate=challenge_type_hard_success_rate,
        # Snooze history
        current_session_snooze_count=current_session_snooze_count,
        current_session_snooze_duration_minutes=current_session_snooze_duration_minutes,
        current_session_wake_delay_seconds=current_session_wake_delay_seconds,
        # Alarm context
        alarm_scheduled_hour=alarm_scheduled_hour,
        alarm_scheduled_minute=alarm_scheduled_minute,
        alarm_day_of_week=alarm_day_of_week,
        alarm_is_weekend=alarm_is_weekend,
        historical_snooze_avg_around_alarm_time=historical_snooze_avg_around_alarm_time,
        # Current context
        selected_challenge_type=challenge_type,
        user_selected_difficulty=difficulty_preference,
        is_adaptive_preference=is_adaptive_preference,
        # Targets: None by default
        target_is_successful=None,
        target_duration_seconds=None,
        target_verification_score=None,
        target_attempt_number=current_attempt_number,
    )


def extract_features_for_attempt(
    db: Session,
    attempt: ChallengeAttempt,
) -> ChallengeFeatureRecord:
    """Extract canonical feature record for a recorded ChallengeAttempt.

    Extracts historical and pre-attempt features strictly up to attempt.started_at,
    and attaches the attempt's outcome fields strictly as target labels (target_*).

    CRITICAL LEAKAGE RULE:
    The target labels are isolated in target_* fields and are NOT used to compute
    any of the 28 input features.
    """
    wake_session = attempt.wake_session
    if wake_session is None:
        wake_session = db.get(WakeSession, attempt.wake_session_id)
        if not wake_session:
            raise ValueError(f"WakeSession {attempt.wake_session_id} not found for attempt {attempt.id}")

    # Determine user difficulty preference from alarm if available
    difficulty_pref = attempt.difficulty_level
    if wake_session.alarm_id:
        alarm = db.get(Alarm, wake_session.alarm_id)
        if alarm and alarm.difficulty_preference:
            difficulty_pref = alarm.difficulty_preference

    # Pre-attempt reference timestamp: exactly when the attempt started
    ref_time = attempt.started_at

    record = extract_features_for_session_context(
        db=db,
        wake_session=wake_session,
        challenge_type=attempt.challenge_type,
        difficulty_preference=difficulty_pref,
        ref_time=ref_time,
        current_attempt_id=attempt.id,
        current_attempt_number=attempt.attempt_number,
    )

    # Attach supervised targets strictly to the target_* fields
    if attempt.is_successful is not None:
        record.target_is_successful = 1 if attempt.is_successful else 0
    else:
        record.target_is_successful = None

    record.target_duration_seconds = attempt.duration_seconds
    record.target_verification_score = attempt.verification_score
    record.target_attempt_number = attempt.attempt_number

    return record
