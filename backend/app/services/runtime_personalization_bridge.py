"""Runtime Personalization Bridge for SmartWake AI (Phase 4.7-A).

Acts as the runtime integration boundary connecting live WakeSession and historical
database records to the Phase 4.5 Challenge Personalization and Precedence Engine:

    Live WakeSession + DB Historical Records
                     ↓
        RuntimePersonalizationBridge (THIS MODULE)
         ├── 1. Behavioral Signal Extraction (pre-T0 snooze, retries, success rate, failures)
         ├── 2. Safe Context Sanitization (zero PII, zero DB IDs, bounded styling hints)
         ├── 3. Recent Structural Signature Collection (bounded LRU, repetition avoidance)
         └── 4. Authoritative Profile Construction (ChallengePersonalizationService)
                     ↓
         RuntimePersonalizationBundle (PersonalizedChallengeProfile)
                     ↓
         PersonalizationDispatcher (Typed Generator Input Contracts for Phase 4.7-B)

CRITICAL INVARIANTS & STRICT BOUNDARIES:
1. USER SOVEREIGNTY:
   - Challenge type chosen by user is strictly preserved; ML/GenAI never alters or mutates it.
   - Alarm time is strictly inviolable; never altered by ML or GenAI.
   - Explicit user-selected difficulty is preserved with absolute precedence.
2. ZERO TELEMETRY FABRICATION:
   - Cold-start / insufficient-history uses existing defaults (historical_success_rate=None,
     recent_failure_count=0) rather than fabricating synthetic historical records.
3. STRICT PRIVACY & DATA ISOLATION:
   - Zero database primary keys (user_id, alarm_id, session_id, wake_session_id) or PII
     enter the GenAI SafePersonalizationContext.
4. PURE PRE-T0 BOUNDARY:
   - Evaluates strictly historical telemetry prior to the current attempt execution.
   - Zero post-challenge outcome leakage.
5. DETERMINISTIC & TESTABLE:
   - Pure, deterministic extraction and mapping based on actual database state.
"""
import json
from typing import Any, Dict, List, Literal, Optional, Sequence, Union, cast
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.constants import FORBIDDEN_CHALLENGE_TYPES, VALID_CHALLENGE_TYPES
from backend.app.core.exceptions import (
    InvalidChallengeTypeError,
    InvalidDifficultyError,
    SmartWakeException,
)
from backend.app.models.challenge_attempt import ChallengeAttempt
from backend.app.models.wake_session import WakeSession
from backend.app.schemas.challenge_content_schemas import (
    FORBIDDEN_CONTEXT_KEYS,
    SafePersonalizationContext,
)
from backend.app.schemas.personalization_content_schemas import (
    BehavioralPersonalizationSignals,
    CanonicalChallengeType,
    CanonicalDifficultyLevel,
    PersonalizedChallengeProfile,
    VALID_CANONICAL_CHALLENGE_TYPES,
    VALID_CANONICAL_DIFFICULTIES,
)
from backend.app.services.genai.challenge_personalization_service import (
    ChallengePersonalizationService,
    sanitize_input_signatures,
)
from backend.app.services.genai.structural_repetition import (
    MAX_WINDOW_CAPACITY,
    validate_structural_signature,
)
from backend.app.services.personalization_dispatcher import (
    PersonalizationDispatchResult,
    PersonalizationDispatcher,
)


class RuntimeBridgeError(SmartWakeException, ValueError):
    """Base domain exception for runtime personalization bridge errors."""
    pass


class RuntimeBridgeTypeError(RuntimeBridgeError, InvalidChallengeTypeError):
    """Raised when an invalid or forbidden challenge type is supplied to the bridge."""
    pass


class RuntimeBridgeDifficultyError(RuntimeBridgeError, InvalidDifficultyError):
    """Raised when an invalid difficulty level is supplied to the bridge."""
    pass


class RuntimePersonalizationBundle(BaseModel):
    """Encapsulates the complete extracted and synthesized runtime personalization artifacts.

    Serves as the clean data transfer object between Phase 4.7-A (extraction) and
    Phase 4.7-B (GenAI generation, safety orchestration, and challenge activation).
    """

    challenge_type: CanonicalChallengeType = Field(
        ...,
        description="Preserved authoritative canonical challenge type.",
    )
    difficulty_level: CanonicalDifficultyLevel = Field(
        ...,
        description="Preserved authoritative concrete difficulty tier ('easy', 'medium', 'hard').",
    )
    safe_context: SafePersonalizationContext = Field(
        ...,
        description="Sanitized explicit user preferences with zero PII or DB IDs.",
    )
    behavioral_signals: BehavioralPersonalizationSignals = Field(
        ...,
        description="Pre-T0 behavioral metrics extracted from actual database history.",
    )
    recent_structural_signatures: List[str] = Field(
        default_factory=list,
        max_length=5,
        description="Bounded list of recent structural signatures (max 5) for repetition avoidance.",
    )
    personalized_profile: PersonalizedChallengeProfile = Field(
        ...,
        description="Authoritative PersonalizedChallengeProfile produced by ChallengePersonalizationService.",
    )

    model_config = ConfigDict(extra="forbid", strict=True)


class RuntimePersonalizationBridge:
    """Runtime bridge coordinating DB extraction and GenAI personalization inputs."""

    @staticmethod
    def canonicalize_challenge_type(challenge_type: str) -> CanonicalChallengeType:
        """Validate and canonicalize challenge category string.

        Enforces strict non-number-guessing and canonical challenge types.
        """
        clean = challenge_type.strip().lower() if challenge_type else ""
        if clean in FORBIDDEN_CHALLENGE_TYPES:
            raise RuntimeBridgeTypeError(
                f"Challenge type '{challenge_type}' is strictly forbidden. "
                "Memory challenges must NOT be implemented as number guessing."
            )
        if clean not in VALID_CANONICAL_CHALLENGE_TYPES:
            raise RuntimeBridgeTypeError(
                f"Invalid challenge type '{challenge_type}'. Must be one of: {sorted(list(VALID_CANONICAL_CHALLENGE_TYPES))}."
            )
        return cast(CanonicalChallengeType, clean)

    @staticmethod
    def canonicalize_difficulty_level(difficulty_level: str) -> CanonicalDifficultyLevel:
        """Validate and canonicalize difficulty level string.

        Requires concrete difficulty tier ('easy', 'medium', 'hard').
        'adaptive' must already be resolved by AdaptiveDecisionEngine prior to bridge.
        """
        clean = difficulty_level.strip().lower() if difficulty_level else ""
        if clean not in VALID_CANONICAL_DIFFICULTIES:
            raise RuntimeBridgeDifficultyError(
                f"Invalid concrete difficulty level '{difficulty_level}'. Must be one of: {sorted(list(VALID_CANONICAL_DIFFICULTIES))}."
            )
        return cast(CanonicalDifficultyLevel, clean)

    @classmethod
    def map_snooze_count_to_level(
        cls, snooze_count: int
    ) -> Literal["none", "low", "moderate", "high"]:
        """Deterministically map session snooze count to behavioral snooze level."""
        if snooze_count <= 0:
            return "none"
        elif snooze_count == 1:
            return "low"
        elif snooze_count == 2:
            return "moderate"
        else:
            return "high"

    @classmethod
    def extract_behavioral_signals(
        cls,
        db: Session,
        wake_session: WakeSession,
        challenge_type: str,
        current_attempt_number: int = 1,
    ) -> BehavioralPersonalizationSignals:
        """Extract pre-T0 behavioral personalization signals strictly from actual database records.

        Rules:
        - Snooze level is derived from wake_session.total_snooze_count.
        - is_retry_attempt is True if current_attempt_number > 1 or prior attempts exist in session.
        - historical_success_rate is calculated across completed attempts for this challenge_type prior to T0.
          Returns None if no historical attempts exist (cold-start). Zero synthetic data.
        - recent_failure_count is the consecutive count of most recent failures prior to T0 (0 to 10).
        """
        clean_type = cls.canonicalize_challenge_type(challenge_type)

        # 1. Map session snooze count to behavioral snooze intensity
        snooze_count = int(wake_session.total_snooze_count or 0)
        snooze_level = cls.map_snooze_count_to_level(snooze_count)

        # 2. Query intra-session prior attempts (retries within current wake session)
        intra_stmt = (
            select(ChallengeAttempt)
            .where(
                ChallengeAttempt.wake_session_id == wake_session.id,
                ChallengeAttempt.attempt_number < current_attempt_number,
                ChallengeAttempt.completed_at.isnot(None),
            )
            .order_by(ChallengeAttempt.attempt_number.desc())
        )
        intra_attempts = list(db.scalars(intra_stmt).all())

        is_retry = (current_attempt_number > 1) or (len(intra_attempts) > 0)

        # 3. Query historical attempts from prior sessions (strictly prior to current session)
        inter_stmt = (
            select(ChallengeAttempt)
            .join(WakeSession, ChallengeAttempt.wake_session_id == WakeSession.id)
            .where(
                WakeSession.user_id == wake_session.user_id,
                WakeSession.id != wake_session.id,
                WakeSession.scheduled_time <= wake_session.scheduled_time,
                ChallengeAttempt.challenge_type == clean_type,
                ChallengeAttempt.completed_at.isnot(None),
            )
            .order_by(ChallengeAttempt.completed_at.desc(), ChallengeAttempt.id.desc())
        )
        inter_attempts = list(db.scalars(inter_stmt).all())

        # Filter intra-attempts to matching challenge_type for consistent performance stats
        matching_intra = [a for a in intra_attempts if str(a.challenge_type).lower() == clean_type]

        # Prior attempts in chronological reverse (newest first): intra-session first, then inter-session
        all_prior = matching_intra + inter_attempts

        # 4. Compute historical success rate across completed attempts with non-None outcome
        completed_outcomes = [a for a in all_prior if a.is_successful is not None]
        hist_success_rate: Optional[float] = None
        if completed_outcomes:
            successes = sum(1 for a in completed_outcomes if a.is_successful is True)
            hist_success_rate = round(float(successes) / len(completed_outcomes), 4)

        # 5. Compute recent consecutive failure count
        recent_failures = 0
        for a in all_prior:
            if a.is_successful is False:
                recent_failures += 1
            elif a.is_successful is True:
                break

        recent_failure_count = min(10, recent_failures)

        return BehavioralPersonalizationSignals(
            recent_snooze_level=snooze_level,
            is_retry_attempt=is_retry,
            historical_success_rate=hist_success_rate,
            recent_failure_count=recent_failure_count,
        )

    @classmethod
    def build_safe_context(
        cls,
        wake_session: WakeSession,
        current_attempt_number: int = 1,
        explicit_context: Optional[Union[SafePersonalizationContext, Dict[str, Any]]] = None,
    ) -> SafePersonalizationContext:
        """Sanitize and build SafePersonalizationContext with guaranteed zero PII / DB IDs.

        Preserves only allowed user preferences (duration hint, preferred theme, language,
        disallowed topics) alongside bounded session metadata (snooze count, attempt number).
        """
        snooze_count = min(20, max(0, int(wake_session.total_snooze_count or 0)))
        bounded_attempt = min(10, max(1, int(current_attempt_number)))

        if explicit_context is None:
            return SafePersonalizationContext(
                current_session_snooze_count=snooze_count,
                current_attempt_number=bounded_attempt,
            )

        if isinstance(explicit_context, SafePersonalizationContext):
            return SafePersonalizationContext(
                desired_duration_seconds=explicit_context.desired_duration_seconds,
                current_session_snooze_count=snooze_count,
                current_attempt_number=bounded_attempt,
                preferred_theme=explicit_context.preferred_theme,
                language=explicit_context.language,
                disallowed_topics=explicit_context.disallowed_topics,
            )

        if isinstance(explicit_context, dict):
            # Strip all forbidden context keys and credential/security fields without false positives on legitimate words
            sanitized: Dict[str, Any] = {}
            for k, v in explicit_context.items():
                k_lower = str(k).strip().lower()
                if k_lower in FORBIDDEN_CONTEXT_KEYS:
                    continue
                # Bounded pattern matching for credential, identity, and security fields
                is_security_key = False
                # Check identity and credential prefixes/suffixes
                if any(k_lower == p or k_lower.startswith(f"{p}_") or k_lower.endswith(f"_{p}") or f"_{p}_" in k_lower
                       for p in ("id", "user", "session", "alarm", "token", "auth", "secret", "cred", "pass", "password", "passphrase")):
                    is_security_key = True
                # Check bounded key patterns (avoids rejecting legitimate words like 'keyboard' or 'hockey')
                if any(k_lower == p or k_lower.startswith(f"{p}_") or k_lower.endswith(f"_{p}") or f"_{p}_" in k_lower
                       for p in ("key", "apikey", "api_key", "jwt", "bearer")):
                    is_security_key = True

                if is_security_key:
                    continue

                sanitized[k] = v

            duration = sanitized.get("desired_duration_seconds")
            theme = sanitized.get("preferred_theme")
            lang = sanitized.get("language", "en")
            topics = sanitized.get("disallowed_topics", [])

            return SafePersonalizationContext(
                desired_duration_seconds=int(duration) if duration is not None else None,
                current_session_snooze_count=snooze_count,
                current_attempt_number=bounded_attempt,
                preferred_theme=str(theme) if theme is not None else None,
                language=str(lang) if lang is not None else "en",
                disallowed_topics=list(topics) if isinstance(topics, (list, tuple)) else [],
            )

        return SafePersonalizationContext(
            current_session_snooze_count=snooze_count,
            current_attempt_number=bounded_attempt,
        )

    @classmethod
    def collect_recent_structural_signatures(
        cls,
        db: Session,
        wake_session: WakeSession,
        challenge_type: str,
        max_capacity: int = MAX_WINDOW_CAPACITY,
    ) -> List[str]:
        """Collect and sanitize recent structural signatures for repetition avoidance.

        Queries recent completed attempts for this user and challenge type, extracts
        structural signatures if persisted in prompt_content, and sanitizes via
        sanitize_input_signatures.
        """
        clean_type = cls.canonicalize_challenge_type(challenge_type)

        # Query recent attempts for this user and challenge type (most recent first)
        stmt = (
            select(ChallengeAttempt)
            .join(WakeSession, ChallengeAttempt.wake_session_id == WakeSession.id)
            .where(
                WakeSession.user_id == wake_session.user_id,
                ChallengeAttempt.challenge_type == clean_type,
                ChallengeAttempt.completed_at.isnot(None),
                ChallengeAttempt.prompt_content.isnot(None),
            )
            .order_by(ChallengeAttempt.completed_at.desc(), ChallengeAttempt.id.desc())
            .limit(max_capacity * 2)  # inspect candidate pool
        )
        recent_attempts = list(db.scalars(stmt).all())

        raw_signatures: List[str] = []
        for attempt in recent_attempts:
            if not attempt.prompt_content:
                continue
            try:
                payload = json.loads(attempt.prompt_content)
                if isinstance(payload, dict):
                    sig = payload.get("structural_signature")
                    if isinstance(sig, str) and sig.strip():
                        raw_signatures.append(sig.strip())
            except (json.JSONDecodeError, Exception):
                continue

        # Sanitize, bound to max_capacity (<= 5), validate security bounds
        return sanitize_input_signatures(raw_signatures, max_capacity=max_capacity)

    @classmethod
    def build_runtime_profile(
        cls,
        db: Session,
        wake_session: WakeSession,
        challenge_type: str,
        difficulty_level: str,
        current_attempt_number: int = 1,
        explicit_context: Optional[Union[SafePersonalizationContext, Dict[str, Any]]] = None,
        personalization_service: Optional[ChallengePersonalizationService] = None,
    ) -> RuntimePersonalizationBundle:
        """Construct the complete RuntimePersonalizationBundle under authoritative precedence.

        1. Validates canonical challenge type and concrete difficulty tier.
        2. Extracts behavioral signals from database strictly before T0.
        3. Sanitizes safe context with zero PII or database IDs.
        4. Collects recent structural signatures for repetition avoidance.
        5. Executes ChallengePersonalizationService precedence engine.
        6. Assembles immutable RuntimePersonalizationBundle.
        """
        clean_type = cls.canonicalize_challenge_type(challenge_type)
        clean_diff = cls.canonicalize_difficulty_level(difficulty_level)

        behavioral_signals = cls.extract_behavioral_signals(
            db=db,
            wake_session=wake_session,
            challenge_type=clean_type,
            current_attempt_number=current_attempt_number,
        )

        safe_context = cls.build_safe_context(
            wake_session=wake_session,
            current_attempt_number=current_attempt_number,
            explicit_context=explicit_context,
        )

        signatures = cls.collect_recent_structural_signatures(
            db=db,
            wake_session=wake_session,
            challenge_type=clean_type,
        )

        service = personalization_service or ChallengePersonalizationService()
        profile = service.personalize(
            challenge_type=clean_type,
            difficulty_level=clean_diff,
            safe_context=safe_context,
            behavioral_signals=behavioral_signals,
            recent_structural_signatures=signatures,
        )

        return RuntimePersonalizationBundle(
            challenge_type=clean_type,
            difficulty_level=clean_diff,
            safe_context=safe_context,
            behavioral_signals=behavioral_signals,
            recent_structural_signatures=signatures,
            personalized_profile=profile,
        )

    @classmethod
    def dispatch_runtime_bundle(
        cls,
        bundle: RuntimePersonalizationBundle,
        dispatcher: Optional[PersonalizationDispatcher] = None,
    ) -> PersonalizationDispatchResult:
        """Convenience method dispatching a bundle's PersonalizedChallengeProfile.

        Prepares typed generator arguments or procedural adapter results ready
        for consumption in Phase 4.7-B.
        """
        disp = dispatcher or PersonalizationDispatcher()
        return disp.dispatch(bundle.personalized_profile)
