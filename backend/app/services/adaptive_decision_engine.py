"""Adaptive Decision Engine for SmartWake AI (Phase 3.4).

Acts as the authoritative runtime decision boundary between the PersonalizationEngine
(Phase 3.3) and Challenge Generation / Challenge Execution (Phase 2.7–2.9).

RESPONSIBILITIES:
1. Validates requested challenge context and input parameters.
2. Preserves user sovereignty:
   - Challenge type chosen by user is strictly preserved; ML never selects or mutates it.
   - Alarm scheduled time is never modified.
   - Fixed difficulty preferences ('easy', 'medium', 'hard') strictly bypass ML inference
     and adaptive guardrails with absolute precedence.
3. Invokes PersonalizationEngine only when difficulty preference is 'adaptive'.
4. Validates output from PersonalizationEngine:
   - Prevents invalid difficulty tiers (e.g. 'adaptive' as a final level).
   - Prevents challenge type mutation.
   - Enforces model confidence threshold (0.60 for ml_adaptive).
5. Produces ONE authoritative, deterministic AdaptiveChallengeDecision object consumed
   by runtime challenge generation.
6. Zero post-challenge leakage (historical/pre-challenge information only).
7. Zero runtime telemetry fabrication (no synthetic generators or fake metrics).
"""
from typing import Any, Dict, List, Optional, Union
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.constants import FORBIDDEN_CHALLENGE_TYPES, VALID_CHALLENGE_TYPES
from backend.app.core.exceptions import InvalidChallengeTypeError, InvalidDifficultyError
from backend.app.models.alarm import Alarm
from backend.app.models.challenge_attempt import ChallengeAttempt
from backend.app.models.wake_session import WakeSession
from backend.app.schemas.personalization_schemas import (
    VALID_DECISION_SOURCES,
    VALID_DIFFICULTY_LEVELS,
    VALID_DIFFICULTY_PREFERENCES,
    AdaptiveChallengeDecision,
    DecisionSource,
    DifficultyLevel,
    DifficultyPreference,
    PersonalizationContext,
    PersonalizationDecision,
)
from backend.app.services.personalization_engine import PersonalizationEngine
from ml.preprocessing.feature_engineering import extract_features_for_session_context
from ml.preprocessing.feature_schema import ChallengeFeatureRecord

# Model confidence threshold established in Phase 3.3
MODEL_CONFIDENCE_THRESHOLD: float = 0.60


class _AdaptiveDecideDispatcher:
    """Descriptor enabling AdaptiveDecisionEngine.decide to function both as an
    instance method (preserving custom-injected PersonalizationEngine) and as a
    class method (instantiating default engine).
    """

    def __get__(
        self,
        obj: Optional["AdaptiveDecisionEngine"],
        objtype: Optional[type] = None,
    ) -> Any:
        if obj is not None:
            def _instance_decide(
                context: Union[PersonalizationContext, Dict[str, Any]],
                feature_record: Optional[Union[ChallengeFeatureRecord, Dict[str, Any]]] = None,
                recent_success_rate: Optional[float] = None,
                recent_avg_duration_seconds: Optional[float] = None,
                has_recent_failure: bool = False,
            ) -> AdaptiveChallengeDecision:
                return obj._decide_impl(
                    context=context,
                    feature_record=feature_record,
                    recent_success_rate=recent_success_rate,
                    recent_avg_duration_seconds=recent_avg_duration_seconds,
                    has_recent_failure=has_recent_failure,
                )

            return _instance_decide
        else:
            def _class_decide(
                context: Union[PersonalizationContext, Dict[str, Any]],
                feature_record: Optional[Union[ChallengeFeatureRecord, Dict[str, Any]]] = None,
                recent_success_rate: Optional[float] = None,
                recent_avg_duration_seconds: Optional[float] = None,
                has_recent_failure: bool = False,
                personalization_engine: Optional[PersonalizationEngine] = None,
            ) -> AdaptiveChallengeDecision:
                engine = (objtype or AdaptiveDecisionEngine)(
                    personalization_engine=personalization_engine
                )
                return engine._decide_impl(
                    context=context,
                    feature_record=feature_record,
                    recent_success_rate=recent_success_rate,
                    recent_avg_duration_seconds=recent_avg_duration_seconds,
                    has_recent_failure=has_recent_failure,
                )

            return _class_decide


class AdaptiveDecisionEngine:
    """Runtime decision boundary between PersonalizationEngine and Challenge Execution."""

    decide = _AdaptiveDecideDispatcher()

    def __init__(
        self,
        personalization_engine: Optional[PersonalizationEngine] = None,
    ) -> None:
        """Initialize AdaptiveDecisionEngine with an optional PersonalizationEngine."""
        self.personalization_engine = personalization_engine or PersonalizationEngine()

    def _decide_impl(
        self,
        context: Union[PersonalizationContext, Dict[str, Any]],
        feature_record: Optional[Union[ChallengeFeatureRecord, Dict[str, Any]]] = None,
        recent_success_rate: Optional[float] = None,
        recent_avg_duration_seconds: Optional[float] = None,
        has_recent_failure: bool = False,
    ) -> AdaptiveChallengeDecision:
        """Internal authoritative decision implementation."""
        # 1. Validate input context
        if context is None:
            raise ValueError("context is required and cannot be None.")

        if isinstance(context, dict):
            ctx = PersonalizationContext(**context)
        elif isinstance(context, PersonalizationContext):
            ctx = context
        else:
            raise ValueError(
                f"context must be PersonalizationContext or dict, got {type(context).__name__}."
            )

        # 2. Strict validation of challenge type and preference
        challenge_type = ctx.challenge_type.strip().lower()
        if challenge_type in FORBIDDEN_CHALLENGE_TYPES:
            raise InvalidChallengeTypeError(
                f"Forbidden challenge type '{challenge_type}'. Memory challenges strictly forbid number guessing."
            )
        if challenge_type not in VALID_CHALLENGE_TYPES:
            raise InvalidChallengeTypeError(
                f"Invalid challenge type '{challenge_type}'. Must be one of: {sorted(list(VALID_CHALLENGE_TYPES))}."
            )

        diff_pref = ctx.difficulty_preference.strip().lower()
        if diff_pref not in VALID_DIFFICULTY_PREFERENCES:
            raise InvalidDifficultyError(
                f"Invalid difficulty preference '{diff_pref}'. Must be one of: {sorted(list(VALID_DIFFICULTY_PREFERENCES))}."
            )

        # 3. Fixed difficulty preference evaluation (Absolute User Precedence)
        # Fixed preferences MUST bypass adaptive ML decisions and adaptive guardrails.
        if diff_pref in (
            DifficultyLevel.EASY.value,
            DifficultyLevel.MEDIUM.value,
            DifficultyLevel.HARD.value,
        ):
            return AdaptiveChallengeDecision(
                challenge_type=challenge_type,
                final_difficulty=diff_pref,
                decision_source=DecisionSource.USER_FIXED.value,
                model_confidence=None,
                raw_model_prediction=None,
                guardrail_applied=False,
                guardrail_reason=None,
                user_id=ctx.user_id,
                wake_session_id=ctx.wake_session_id,
                alarm_id=ctx.alarm_id,
                decision_rationale=(
                    f"User fixed difficulty '{diff_pref}' applied directly. "
                    "Bypassed ML inference and adaptive guardrails."
                ),
                feature_snapshot={},
            )

        # 4. Adaptive difficulty preference: invoke PersonalizationEngine
        raw_decision: PersonalizationDecision = self.personalization_engine.decide(
            context=ctx,
            feature_record=feature_record,
            recent_success_rate=recent_success_rate,
            recent_avg_duration_seconds=recent_avg_duration_seconds,
            has_recent_failure=has_recent_failure,
        )

        # 5. Rigorous boundary validation of PersonalizationEngine output
        # Invariant A: Challenge type must never be altered or replaced
        if raw_decision.challenge_type.strip().lower() != challenge_type:
            raise ValueError(
                f"PersonalizationEngine mutated challenge type from '{challenge_type}' "
                f"to '{raw_decision.challenge_type}'. Challenge type mutation is strictly forbidden."
            )

        # Invariant B: Final difficulty must be concrete ('easy', 'medium', 'hard')
        final_diff = raw_decision.recommended_difficulty.strip().lower()
        if final_diff not in VALID_DIFFICULTY_LEVELS:
            raise ValueError(
                f"PersonalizationEngine produced invalid final difficulty '{final_diff}'. "
                f"Must be concrete tier in: {VALID_DIFFICULTY_LEVELS}."
            )

        # Invariant C: Decision source must be recognized
        decision_src = raw_decision.decision_source
        if decision_src not in VALID_DECISION_SOURCES:
            raise ValueError(
                f"PersonalizationEngine returned unrecognized decision source '{decision_src}'."
            )

        # Invariant D: ML confidence threshold verification
        if decision_src == DecisionSource.ML_ADAPTIVE.value:
            if (
                raw_decision.model_confidence is None
                or raw_decision.model_confidence < MODEL_CONFIDENCE_THRESHOLD
            ):
                raise ValueError(
                    f"Decision source is ml_adaptive but confidence "
                    f"({raw_decision.model_confidence}) is below required threshold ({MODEL_CONFIDENCE_THRESHOLD})."
                )

        # Invariant E: Validate raw ML prediction tier if present
        if raw_decision.raw_model_prediction is not None:
            raw_pred = raw_decision.raw_model_prediction.strip().lower()
            if raw_pred not in VALID_DIFFICULTY_LEVELS:
                raise ValueError(
                    f"PersonalizationEngine returned invalid raw model prediction '{raw_pred}'."
                )

        # 6. Construct explainable decision rationale
        rationale: str
        if decision_src == DecisionSource.COLD_START_STAGE_0.value:
            rationale = (
                f"Stage 0 cold-start heuristic: resolved to '{final_diff}' based on "
                f"task demand ('{challenge_type}') and session snooze count ({ctx.current_session_snooze_count})."
            )
        elif decision_src == DecisionSource.COLD_START_STAGE_1.value:
            rationale = (
                f"Stage 1 contextual rules: resolved to '{final_diff}' based on "
                f"prior session performance and completion metrics."
            )
        elif decision_src == DecisionSource.ML_ADAPTIVE.value:
            conf_str = f"{raw_decision.model_confidence:.2f}" if raw_decision.model_confidence else "N/A"
            rationale = (
                f"Stage 2 ML adaptive: baseline model predicted '{raw_decision.raw_model_prediction}' "
                f"with confidence {conf_str} (>= {MODEL_CONFIDENCE_THRESHOLD})."
            )
        elif decision_src == DecisionSource.GUARDRAIL_CLAMPED.value:
            rationale = (
                f"Guardrail clamped: final difficulty adjusted to '{final_diff}' "
                f"due to: {raw_decision.guardrail_reason}."
            )
        elif decision_src == DecisionSource.FALLBACK_SAFE.value:
            rationale = (
                f"Safe fallback: resolved to '{final_diff}' due to low model confidence "
                f"(< {MODEL_CONFIDENCE_THRESHOLD}) or missing historical telemetry."
            )
        else:
            rationale = f"Resolved to '{final_diff}' via {decision_src}."

        # 7. Construct and return authoritative AdaptiveChallengeDecision
        return AdaptiveChallengeDecision(
            challenge_type=challenge_type,
            final_difficulty=final_diff,
            decision_source=decision_src,
            model_confidence=raw_decision.model_confidence,
            raw_model_prediction=raw_decision.raw_model_prediction,
            guardrail_applied=raw_decision.guardrail_applied,
            guardrail_reason=raw_decision.guardrail_reason,
            user_id=ctx.user_id,
            wake_session_id=ctx.wake_session_id,
            alarm_id=ctx.alarm_id,
            decision_rationale=rationale,
            feature_snapshot=raw_decision.feature_snapshot or {},
        )

    @classmethod
    def decide_for_session(
        cls,
        db: Session,
        wake_session: WakeSession,
        challenge_type: Optional[str] = None,
        difficulty_preference: Optional[str] = None,
        current_attempt_number: int = 1,
        personalization_engine: Optional[PersonalizationEngine] = None,
    ) -> AdaptiveChallengeDecision:
        """Authoritative database-backed decision for an active WakeSession.

        Safely inspects prior database records strictly BEFORE the current attempt
        starts (preserving point-in-time rules and avoiding post-challenge leakage).
        Extracts available telemetry without fabricating synthetic values.

        Args:
            db: Active SQLAlchemy database session.
            wake_session: Current WakeSession being executed.
            challenge_type: Optional explicit challenge category (defaults to alarm or 'math').
            difficulty_preference: Optional difficulty preference (defaults to alarm or 'adaptive').
            current_attempt_number: Current attempt sequence number (1 for initial, 2+ for retries).
            personalization_engine: Optional custom PersonalizationEngine for testing.

        Returns:
            AdaptiveChallengeDecision: Authoritative decision consumed by runtime generator.
        """
        # 1. Resolve user-selected challenge type
        target_type: str
        if challenge_type:
            target_type = str(challenge_type)
        elif wake_session.alarm_id:
            alarm = db.get(Alarm, wake_session.alarm_id)
            target_type = str(alarm.selected_challenge_type) if alarm else "math"
        else:
            target_type = "math"

        # 2. Resolve difficulty preference
        target_pref: str
        if difficulty_preference:
            target_pref = str(difficulty_preference)
        elif wake_session.alarm_id:
            alarm = db.get(Alarm, wake_session.alarm_id)
            target_pref = (
                str(alarm.difficulty_preference) if (alarm and alarm.difficulty_preference) else "adaptive"
            )
        else:
            target_pref = "adaptive"

        clean_pref = target_pref.strip().lower()

        # 3. Fast-path for fixed user preferences (bypass all DB feature queries & ML)
        if clean_pref in (
            DifficultyLevel.EASY.value,
            DifficultyLevel.MEDIUM.value,
            DifficultyLevel.HARD.value,
        ):
            ctx = PersonalizationContext(
                user_id=int(wake_session.user_id),
                wake_session_id=int(wake_session.id),
                alarm_id=int(wake_session.alarm_id) if wake_session.alarm_id is not None else None,
                challenge_type=target_type,
                difficulty_preference=clean_pref,
                current_session_snooze_count=int(wake_session.total_snooze_count),
                historical_session_count=0,
                previous_difficulty=None,
            )
            engine = cls(personalization_engine=personalization_engine)
            return engine.decide(context=ctx)

        # 4. Adaptive preference: query point-in-time historical data
        # Query prior completed/abandoned sessions strictly before this session's scheduled time
        prior_sessions_query = (
            select(WakeSession)
            .where(
                WakeSession.user_id == wake_session.user_id,
                WakeSession.id != wake_session.id,
                WakeSession.scheduled_time <= wake_session.scheduled_time,
                WakeSession.status.in_(["completed", "abandoned"]),
            )
            .order_by(WakeSession.scheduled_time.desc(), WakeSession.id.desc())
        )
        prior_sessions = list(db.scalars(prior_sessions_query).all())
        historical_session_count = len(prior_sessions)

        # Resolve previous_difficulty:
        # Check intra-session prior attempts first (retries)
        previous_difficulty: Optional[str] = None
        if current_attempt_number > 1:
            intra_prior_query = (
                select(ChallengeAttempt)
                .where(
                    ChallengeAttempt.wake_session_id == wake_session.id,
                    ChallengeAttempt.attempt_number < current_attempt_number,
                )
                .order_by(ChallengeAttempt.attempt_number.desc())
            )
            intra_prior = db.scalars(intra_prior_query).first()
            if intra_prior and str(intra_prior.difficulty_level) in VALID_DIFFICULTY_LEVELS:
                previous_difficulty = str(intra_prior.difficulty_level)

        # If not found in current session, check prior historical attempts
        if not previous_difficulty and prior_sessions:
            prior_session_ids = [s.id for s in prior_sessions]
            prior_attempt_query = (
                select(ChallengeAttempt)
                .where(
                    ChallengeAttempt.wake_session_id.in_(prior_session_ids),
                    ChallengeAttempt.completed_at.isnot(None),
                    ChallengeAttempt.is_successful == True,  # noqa: E712
                )
                .order_by(ChallengeAttempt.completed_at.desc())
            )
            last_attempt = db.scalars(prior_attempt_query).first()
            if last_attempt and str(last_attempt.difficulty_level) in VALID_DIFFICULTY_LEVELS:
                previous_difficulty = str(last_attempt.difficulty_level)

        # Build PersonalizationContext
        ctx = PersonalizationContext(
            user_id=int(wake_session.user_id),
            wake_session_id=int(wake_session.id),
            alarm_id=int(wake_session.alarm_id) if wake_session.alarm_id is not None else None,
            challenge_type=target_type,
            difficulty_preference="adaptive",
            current_session_snooze_count=int(wake_session.total_snooze_count),
            historical_session_count=historical_session_count,
            previous_difficulty=previous_difficulty,
        )

        # 5. Extract features if Stage 2 (8+ historical sessions)
        feature_record: Optional[ChallengeFeatureRecord] = None
        if historical_session_count >= 8:
            feature_record = extract_features_for_session_context(
                db=db,
                wake_session=wake_session,
                challenge_type=target_type,
                difficulty_preference="adaptive",
                current_attempt_number=current_attempt_number,
            )

        engine = cls(personalization_engine=personalization_engine)
        return engine.decide(context=ctx, feature_record=feature_record)
