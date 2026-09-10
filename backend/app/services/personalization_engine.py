"""Personalization Engine Services for SmartWake AI (Phase 3.3).

Contains deterministic personalization policies:
1. ColdStartRouter: Lifecycle routing for Stage 0 (heuristics), Stage 1 (contextual rules),
   and Stage 2 (ML model handoff).
2. SafetyGuardrails: Operational safety boundaries enforcing maximum difficulty step-shift
   limits and sleep inertia floors.

PRECEDENCE RULES:
1. User-fixed difficulty is evaluated first (at engine level; bypassed here).
2. Adaptive candidate difficulty is produced (via cold-start router or ML).
3. Maximum step-shift guardrail is applied (+-1 tier relative to previous_difficulty).
4. Sleep-inertia floor guardrail is applied (caps hard at medium if snooze count >= 3).
5. Final difficulty must strictly resolve to 'easy', 'medium', or 'hard'.
   'adaptive' is never a final concrete challenge difficulty.
"""
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union

from backend.app.schemas.personalization_schemas import (
    VALID_DIFFICULTY_LEVELS,
    DecisionSource,
    DifficultyLevel,
    PersonalizationContext,
    PersonalizationDecision,
)
from backend.app.services.model_inference_manager import (
    ModelInferenceManager,
    ModelInferenceResult,
)
from ml.preprocessing.feature_schema import ChallengeFeatureRecord

# Canonical ordering of difficulty levels for step-shift calculations
DIFFICULTY_ORDER: List[str] = [
    DifficultyLevel.EASY.value,
    DifficultyLevel.MEDIUM.value,
    DifficultyLevel.HARD.value,
]
DIFFICULTY_INDEX: Dict[str, int] = {
    diff: idx for idx, diff in enumerate(DIFFICULTY_ORDER)
}

# Task categorization for Stage 0 cold-start heuristics
HIGH_COGNITIVE_CHALLENGES = {"math", "memory"}
PHYSICAL_SPEECH_CHALLENGES = {"dance", "tongue_twister", "push_ups"}


@dataclass
class ColdStartResult:
    """Result from cold-start lifecycle routing.

    Attributes:
        stage: The evaluated cold-start lifecycle stage (0, 1, or 2).
        requires_ml: True if user history warrants full ML model inference (Stage 2).
        candidate_difficulty: Proposed difficulty tier, or None if ML is required.
        decision_source: The associated DecisionSource enum, or None if ML is required.
        rule_reason: Descriptive explanation of the cold-start rule application.
    """

    stage: int
    requires_ml: bool
    candidate_difficulty: Optional[str]
    decision_source: Optional[DecisionSource]
    rule_reason: Optional[str]


@dataclass
class GuardrailResult:
    """Result from applying operational safety guardrails to a candidate difficulty.

    Attributes:
        final_difficulty: The resulting difficulty tier ('easy', 'medium', 'hard').
        guardrail_applied: True if any guardrail modified the candidate difficulty.
        guardrail_reason: Semicolon-separated explanations of applied guardrails, or None.
        raw_difficulty: The original candidate difficulty before guardrails.
        step_shift_applied: True if max step shift clamped the candidate difficulty.
        sleep_inertia_applied: True if sleep inertia floor clamped 'hard' to 'medium'.
    """

    final_difficulty: str
    guardrail_applied: bool
    guardrail_reason: Optional[str]
    raw_difficulty: str
    step_shift_applied: bool
    sleep_inertia_applied: bool


class SafetyGuardrails:
    """Operational safety boundaries for SmartWake AI difficulty adaptation.

    Guarantees:
    1. Maximum Step Shift: Difficulty cannot jump more than +-1 level from
       the previous session baseline (e.g. easy -> hard is clamped to medium).
    2. Sleep Inertia Floor: If current_session_snooze_count >= 3, difficulty is
       capped at 'medium' (never 'hard') to prevent frustration/abandonment.
    3. Output difficulty is strictly concrete ('easy', 'medium', 'hard').
    """

    @staticmethod
    def clamp_step_shift(
        candidate_difficulty: str,
        previous_difficulty: Optional[str],
    ) -> Tuple[str, bool, Optional[str]]:
        """Clamp candidate difficulty to at most +-1 step from previous difficulty.

        Args:
            candidate_difficulty: The candidate difficulty ('easy', 'medium', 'hard').
            previous_difficulty: Previous successful difficulty tier if available.

        Returns:
            Tuple of (clamped_difficulty, was_clamped, clamp_reason).
        """
        cand_clean = candidate_difficulty.strip().lower()
        if cand_clean not in DIFFICULTY_INDEX:
            raise ValueError(
                f"Invalid candidate difficulty '{candidate_difficulty}'. "
                f"Must be one of: {VALID_DIFFICULTY_LEVELS}."
            )

        if not previous_difficulty:
            return cand_clean, False, None

        prev_clean = previous_difficulty.strip().lower()
        if prev_clean not in DIFFICULTY_INDEX:
            return cand_clean, False, None

        cand_idx = DIFFICULTY_INDEX[cand_clean]
        prev_idx = DIFFICULTY_INDEX[prev_clean]
        diff = cand_idx - prev_idx

        if diff > 1:
            clamped_idx = prev_idx + 1
            clamped_diff = DIFFICULTY_ORDER[clamped_idx]
            reason = (
                f"Maximum step shift clamped: candidate '{cand_clean}' clamped to "
                f"'{clamped_diff}' (+1 step from previous '{prev_clean}')"
            )
            return clamped_diff, True, reason
        elif diff < -1:
            clamped_idx = prev_idx - 1
            clamped_diff = DIFFICULTY_ORDER[clamped_idx]
            reason = (
                f"Maximum step shift clamped: candidate '{cand_clean}' clamped to "
                f"'{clamped_diff}' (-1 step from previous '{prev_clean}')"
            )
            return clamped_diff, True, reason

        return cand_clean, False, None

    @staticmethod
    def apply_sleep_inertia_floor(
        difficulty: str,
        current_session_snooze_count: int,
    ) -> Tuple[str, bool, Optional[str]]:
        """Cap difficulty at medium if current session snooze count >= 3.

        Args:
            difficulty: Candidate difficulty tier.
            current_session_snooze_count: Count of snoozes in the current session.

        Returns:
            Tuple of (adjusted_difficulty, was_clamped, clamp_reason).
        """
        clean_diff = difficulty.strip().lower()
        if current_session_snooze_count >= 3 and clean_diff == DifficultyLevel.HARD.value:
            reason = (
                f"Sleep inertia floor applied: snooze count "
                f"({current_session_snooze_count} >= 3) capped 'hard' to 'medium'"
            )
            return DifficultyLevel.MEDIUM.value, True, reason
        return clean_diff, False, None

    @classmethod
    def apply_guardrails(
        cls,
        candidate_difficulty: str,
        previous_difficulty: Optional[str] = None,
        current_session_snooze_count: int = 0,
    ) -> GuardrailResult:
        """Apply all safety guardrails in strict precedence order.

        Precedence:
        1. Max step-shift clamp relative to previous_difficulty.
        2. Sleep inertia floor relative to current snooze count.

        Args:
            candidate_difficulty: The initial candidate difficulty tier.
            previous_difficulty: Optional previous successful difficulty tier.
            current_session_snooze_count: Number of snoozes pressed this morning.

        Returns:
            GuardrailResult with final concrete difficulty and audit telemetry.
        """
        raw = candidate_difficulty.strip().lower()
        reasons: List[str] = []

        # 1. Step-shift guardrail
        after_shift, shift_applied, shift_reason = cls.clamp_step_shift(
            raw, previous_difficulty
        )
        if shift_applied and shift_reason:
            reasons.append(shift_reason)

        # 2. Sleep inertia floor guardrail
        final_diff, inertia_applied, inertia_reason = cls.apply_sleep_inertia_floor(
            after_shift, current_session_snooze_count
        )
        if inertia_applied and inertia_reason:
            reasons.append(inertia_reason)

        guardrail_applied = shift_applied or inertia_applied
        combined_reason = "; ".join(reasons) if reasons else None

        return GuardrailResult(
            final_difficulty=final_diff,
            guardrail_applied=guardrail_applied,
            guardrail_reason=combined_reason,
            raw_difficulty=raw,
            step_shift_applied=shift_applied,
            sleep_inertia_applied=inertia_applied,
        )


class ColdStartRouter:
    """Evaluates the user's historical lifecycle and routes cold-start decisions.

    Lifecycle Stages:
    - Stage 0 (0-3 historical sessions): Pure task-type and snooze heuristics.
    - Stage 1 (4-7 historical sessions): Contextual rules using recent performance.
    - Stage 2 (8+ historical sessions): Active ML policy (unresolved; requires ML).
    """

    @staticmethod
    def get_stage(historical_session_count: int) -> int:
        """Determine lifecycle stage from historical session count."""
        if historical_session_count <= 3:
            return 0
        elif historical_session_count <= 7:
            return 1
        return 2

    @staticmethod
    def evaluate_stage_0(
        challenge_type: str,
        current_session_snooze_count: int = 0,
    ) -> Tuple[str, str]:
        """Evaluate Stage 0 heuristics.

        Rules:
        - math/memory -> easy
        - dance/tongue_twister/push_ups -> medium
        - current_session_snooze_count >= 2 -> downgrade to easy

        Args:
            challenge_type: Canonical challenge type.
            current_session_snooze_count: Snoozes in the current session.

        Returns:
            Tuple of (candidate_difficulty, rule_reason).
        """
        c_clean = challenge_type.strip().lower()

        # Task demand heuristic
        if c_clean in HIGH_COGNITIVE_CHALLENGES:
            base_diff = DifficultyLevel.EASY.value
            reason = f"Stage 0 heuristic: high-cognitive challenge '{c_clean}' defaults to 'easy'."
        else:
            base_diff = DifficultyLevel.MEDIUM.value
            reason = f"Stage 0 heuristic: physical/speech challenge '{c_clean}' defaults to 'medium'."

        # Snooze inertia downgrade heuristic
        if current_session_snooze_count >= 2:
            base_diff = DifficultyLevel.EASY.value
            reason += (
                f" Downgraded to 'easy' due to snooze count "
                f"({current_session_snooze_count} >= 2)."
            )

        return base_diff, reason

    @staticmethod
    def evaluate_stage_1(
        baseline_difficulty: Optional[str] = None,
        recent_success_rate: Optional[float] = None,
        recent_avg_duration_seconds: Optional[float] = None,
        has_recent_failure: bool = False,
    ) -> Tuple[str, str]:
        """Evaluate Stage 1 contextual moving average rules.

        Rules:
        - recent failure OR avg duration > 40.0s -> easy
        - recent success rate == 100% AND avg duration < 15.0s -> promote baseline by +1 level
        - otherwise -> medium

        Args:
            baseline_difficulty: Baseline difficulty to adjust from (defaults to 'medium').
            recent_success_rate: Rolling success rate (1.0 = 100%).
            recent_avg_duration_seconds: Average challenge completion speed in seconds.
            has_recent_failure: True if any recent attempt was failed or abandoned.

        Returns:
            Tuple of (candidate_difficulty, rule_reason).
        """
        base = (
            baseline_difficulty.strip().lower()
            if baseline_difficulty and baseline_difficulty.strip().lower() in DIFFICULTY_INDEX
            else DifficultyLevel.MEDIUM.value
        )

        # 1. Failure / Slow completion demotion rule
        if has_recent_failure or (
            recent_avg_duration_seconds is not None and recent_avg_duration_seconds > 40.0
        ):
            triggers = []
            if has_recent_failure:
                triggers.append("recent failure occurred")
            if recent_avg_duration_seconds is not None and recent_avg_duration_seconds > 40.0:
                triggers.append(
                    f"slow completion time ({recent_avg_duration_seconds:.1f}s > 40s)"
                )
            reason = f"Stage 1 rule: resolved to 'easy' due to {', '.join(triggers)}."
            return DifficultyLevel.EASY.value, reason

        # 2. Mastery promotion rule (100% success rate AND completion time < 15.0s)
        if (
            recent_success_rate is not None
            and recent_success_rate >= 1.0
            and recent_avg_duration_seconds is not None
            and recent_avg_duration_seconds < 15.0
        ):
            curr_idx = DIFFICULTY_INDEX[base]
            promoted_idx = min(curr_idx + 1, len(DIFFICULTY_ORDER) - 1)
            promoted_diff = DIFFICULTY_ORDER[promoted_idx]
            reason = (
                f"Stage 1 rule: 100% success rate and fast completion "
                f"({recent_avg_duration_seconds:.1f}s < 15s) promotes baseline '{base}' to '{promoted_diff}'."
            )
            return promoted_diff, reason

        # 3. Standard balanced engagement rule
        reason = "Stage 1 rule: standard balanced engagement resolves to 'medium'."
        return DifficultyLevel.MEDIUM.value, reason

    @classmethod
    def evaluate_safe_fallback(
        cls,
        challenge_type: str,
        baseline_difficulty: Optional[str] = None,
        recent_success_rate: Optional[float] = None,
        recent_avg_duration_seconds: Optional[float] = None,
        has_recent_failure: bool = False,
        current_session_snooze_count: int = 0,
        trigger_reason: Optional[str] = None,
    ) -> Tuple[str, str]:
        """Authoritative deterministic fallback difficulty resolution (Phase 3.5).

        Used by PersonalizationEngine and AdaptiveDecisionEngine when ML prediction
        is unavailable, low confidence (< 0.60), or historical telemetry is incomplete.

        Rules:
        1. Contextual Telemetry Distinction:
           - Complete telemetry: both success rate and average duration are provided.
           - Partial telemetry: at least one metric is present (e.g. failure flag, or duration, or success rate).
           - Unavailable telemetry: no historical metrics provided.
        2. Policy Resolution:
           - If contextual telemetry exists (complete or partial):
             Evaluates Stage 1 contextual policy.
             * Recent failure or avg duration > 40.0s -> 'easy'
             * 100% success rate AND avg duration < 15.0s -> promotes baseline by +1 level
               (Partial telemetry missing duration or success rate NEVER promotes; zero fabrication)
             * Otherwise -> 'medium'
           - If telemetry is unavailable:
             Falls back to the safest existing deterministic baseline.
             * If baseline_difficulty is provided and current_session_snooze_count < 2:
               preserves baseline_difficulty if 'easy', else 'medium'.
             * If baseline_difficulty is None or current_session_snooze_count >= 2:
               evaluates Stage 0 heuristic (math/memory -> 'easy', snooze >= 2 -> 'easy',
               physical -> 'medium').
        3. Never fabricates missing metrics (no synthetic values).

        Args:
            challenge_type: Canonical challenge type.
            baseline_difficulty: Optional prior difficulty baseline to evaluate against.
            recent_success_rate: Optional rolling success rate (1.0 = 100%).
            recent_avg_duration_seconds: Optional average completion speed in seconds.
            has_recent_failure: True if recent attempt was failed/abandoned.
            current_session_snooze_count: Count of snoozes in current session.
            trigger_reason: Optional diagnostic trigger description.

        Returns:
            Tuple of (candidate_difficulty, rule_reason).
        """
        c_clean = challenge_type.strip().lower()
        has_contextual_telemetry = (
            has_recent_failure
            or recent_avg_duration_seconds is not None
            or recent_success_rate is not None
        )

        prefix = f"Safe fallback ({trigger_reason}): " if trigger_reason else "Safe fallback: "

        if has_contextual_telemetry:
            # Evaluate existing Stage 1 contextual policy
            diff, stage_1_reason = cls.evaluate_stage_1(
                baseline_difficulty=baseline_difficulty,
                recent_success_rate=recent_success_rate,
                recent_avg_duration_seconds=recent_avg_duration_seconds,
                has_recent_failure=has_recent_failure,
            )
            return diff, f"{prefix}{stage_1_reason}"

        # Telemetry is completely unavailable
        if baseline_difficulty and current_session_snooze_count < 2:
            base_clean = baseline_difficulty.strip().lower()
            safe_diff = DifficultyLevel.EASY.value if base_clean == DifficultyLevel.EASY.value else DifficultyLevel.MEDIUM.value
            reason = (
                f"{prefix}telemetry unavailable; defaulted to safest baseline '{safe_diff}' "
                f"from prior baseline '{baseline_difficulty}'."
            )
            return safe_diff, reason

        # Baseline is None or snooze count >= 2: fall back to challenge-specific Stage 0 heuristic
        s0_diff, s0_reason = cls.evaluate_stage_0(
            challenge_type=c_clean,
            current_session_snooze_count=current_session_snooze_count,
        )
        return s0_diff, f"{prefix}telemetry unavailable; applied Stage 0 baseline: {s0_reason}"

    @classmethod
    def route(
        cls,
        context: PersonalizationContext,
        recent_success_rate: Optional[float] = None,
        recent_avg_duration_seconds: Optional[float] = None,
        has_recent_failure: bool = False,
    ) -> ColdStartResult:
        """Route personalization context through the appropriate cold-start stage.

        Note:
            The cold-start router NEVER changes context.challenge_type.

        Args:
            context: PersonalizationContext containing user and session context.
            recent_success_rate: Optional recent 3-session success rate for Stage 1.
            recent_avg_duration_seconds: Optional average completion time for Stage 1.
            has_recent_failure: Optional indicator of recent failure for Stage 1.

        Returns:
            ColdStartResult indicating stage, candidate difficulty, and whether ML is required.
        """
        stage = cls.get_stage(context.historical_session_count)

        if stage == 0:
            diff, reason = cls.evaluate_stage_0(
                challenge_type=context.challenge_type,
                current_session_snooze_count=context.current_session_snooze_count,
            )
            return ColdStartResult(
                stage=0,
                requires_ml=False,
                candidate_difficulty=diff,
                decision_source=DecisionSource.COLD_START_STAGE_0,
                rule_reason=reason,
            )

        elif stage == 1:
            diff, reason = cls.evaluate_stage_1(
                baseline_difficulty=context.previous_difficulty,
                recent_success_rate=recent_success_rate,
                recent_avg_duration_seconds=recent_avg_duration_seconds,
                has_recent_failure=has_recent_failure,
            )
            return ColdStartResult(
                stage=1,
                requires_ml=False,
                candidate_difficulty=diff,
                decision_source=DecisionSource.COLD_START_STAGE_1,
                rule_reason=reason,
            )

        else:
            # Stage 2: 8+ historical sessions
            return ColdStartResult(
                stage=2,
                requires_ml=True,
                candidate_difficulty=None,
                decision_source=None,
                rule_reason=(
                    f"Stage 2: sufficient history ({context.historical_session_count} >= 8 sessions); "
                    "requires ML baseline model inference."
                ),
            )


class _DecideDispatcher:
    """Descriptor enabling PersonalizationEngine.decide to function both as an
    instance method (preserving custom-injected ModelInferenceManager) and as a
    class method (instantiating default manager).
    """

    def __get__(
        self,
        obj: Optional["PersonalizationEngine"],
        objtype: Optional[type] = None,
    ) -> Any:
        if obj is not None:
            def _instance_decide(
                context: Union[PersonalizationContext, Dict[str, Any]],
                feature_record: Optional[Union[ChallengeFeatureRecord, Dict[str, Any]]] = None,
                recent_success_rate: Optional[float] = None,
                recent_avg_duration_seconds: Optional[float] = None,
                has_recent_failure: bool = False,
            ) -> PersonalizationDecision:
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
                model_manager: Optional[ModelInferenceManager] = None,
            ) -> PersonalizationDecision:
                engine = (objtype or PersonalizationEngine)(model_manager=model_manager)
                return engine._decide_impl(
                    context=context,
                    feature_record=feature_record,
                    recent_success_rate=recent_success_rate,
                    recent_avg_duration_seconds=recent_avg_duration_seconds,
                    has_recent_failure=has_recent_failure,
                )

            return _class_decide


class PersonalizationEngine:
    """Core Personalization Engine for SmartWake AI (Step 3.3.4).

    Orchestrates the end-to-end difficulty personalization process:
    A. Validates the personalization context and preserves immutable challenge_type.
    B. Evaluates fixed user preferences with absolute precedence:
       - easy -> easy, medium -> medium, hard -> hard
       - strictly bypasses ML inference and adaptive guardrails
       - decision_source = user_fixed
    C. For adaptive preferences, evaluates lifecycle stage:
       - Stage 0 (0-3 sessions): Pure heuristics via ColdStartRouter (no ML)
       - Stage 1 (4-7 sessions): Contextual rules via ColdStartRouter (no ML)
       - Stage 2 (8+ sessions): ML model inference via ModelInferenceManager
    D. Enforces confidence threshold (0.60):
       - If confidence >= 0.60: candidate is ML predicted difficulty (ml_adaptive)
       - If confidence < 0.60: candidate falls back to Stage 1 contextual heuristic
         without fabricating telemetry (fallback_safe)
    E. Applies SafetyGuardrails to candidate difficulty (for adaptive decisions):
       - Step-shift clamp (+-1 relative to previous difficulty)
       - Sleep-inertia floor (snooze >= 3 clamps hard to medium)
       - Clamped decisions update decision_source to guardrail_clamped
    F. Returns a complete, validated PersonalizationDecision schema instance.
    """

    decide = _DecideDispatcher()

    def __init__(
        self,
        model_manager: Optional[ModelInferenceManager] = None,
    ) -> None:
        """Initialize PersonalizationEngine with an optional ModelInferenceManager."""
        self.model_manager = model_manager or ModelInferenceManager()

    def _decide_impl(
        self,
        context: Union[PersonalizationContext, Dict[str, Any]],
        feature_record: Optional[Union[ChallengeFeatureRecord, Dict[str, Any]]] = None,
        recent_success_rate: Optional[float] = None,
        recent_avg_duration_seconds: Optional[float] = None,
        has_recent_failure: bool = False,
    ) -> PersonalizationDecision:
        """Internal implementation of personalization decision logic."""
        # A. Validate personalization context
        if isinstance(context, dict):
            ctx = PersonalizationContext(**context)
        elif isinstance(context, PersonalizationContext):
            ctx = context
        else:
            raise ValueError(
                f"context must be a PersonalizationContext or dict, got {type(context).__name__}"
            )

        # B. Preserve challenge type exactly
        challenge_type = ctx.challenge_type

        # C. Fixed user preference has absolute precedence
        pref = ctx.difficulty_preference.strip().lower()
        if pref in (
            DifficultyLevel.EASY.value,
            DifficultyLevel.MEDIUM.value,
            DifficultyLevel.HARD.value,
        ):
            return PersonalizationDecision(
                recommended_difficulty=pref,
                challenge_type=challenge_type,
                decision_source=DecisionSource.USER_FIXED.value,
                model_confidence=None,
                raw_model_prediction=None,
                guardrail_applied=False,
                guardrail_reason=None,
                feature_snapshot={},
            )

        # D. Adaptive preference handling
        stage = ColdStartRouter.get_stage(ctx.historical_session_count)

        raw_model_prediction: Optional[str] = None
        model_confidence: Optional[float] = None
        feature_snapshot: Dict[str, Any] = {}

        if stage == 0:
            # Stage 0: Heuristic fallback (0-3 sessions) — never invoke ML
            candidate_diff, rule_reason = ColdStartRouter.evaluate_stage_0(
                challenge_type=challenge_type,
                current_session_snooze_count=ctx.current_session_snooze_count,
            )
            candidate_source = DecisionSource.COLD_START_STAGE_0

        elif stage == 1:
            # Stage 1: Contextual rules (4-7 sessions) — never invoke ML
            # Extract available telemetry without fabrication
            eff_success_rate, eff_duration, eff_has_failure = self._resolve_stage_1_telemetry(
                feature_record=feature_record,
                recent_success_rate=recent_success_rate,
                recent_avg_duration_seconds=recent_avg_duration_seconds,
                has_recent_failure=has_recent_failure,
            )
            candidate_diff, rule_reason = ColdStartRouter.evaluate_stage_1(
                baseline_difficulty=ctx.previous_difficulty,
                recent_success_rate=eff_success_rate,
                recent_avg_duration_seconds=eff_duration,
                has_recent_failure=eff_has_failure,
            )
            candidate_source = DecisionSource.COLD_START_STAGE_1

        else:
            # Stage 2: 8+ sessions — ML inference
            eff_success_rate, eff_duration, eff_has_failure = self._resolve_stage_1_telemetry(
                feature_record=feature_record,
                recent_success_rate=recent_success_rate,
                recent_avg_duration_seconds=recent_avg_duration_seconds,
                has_recent_failure=has_recent_failure,
            )

            if feature_record is None:
                # Level 7: Incomplete/missing telemetry — safe deterministic fallback
                candidate_diff, fallback_reason = ColdStartRouter.evaluate_safe_fallback(
                    challenge_type=challenge_type,
                    baseline_difficulty=ctx.previous_difficulty,
                    recent_success_rate=eff_success_rate,
                    recent_avg_duration_seconds=eff_duration,
                    has_recent_failure=eff_has_failure,
                    current_session_snooze_count=ctx.current_session_snooze_count,
                    trigger_reason="missing feature record/telemetry",
                )
                candidate_source = DecisionSource.FALLBACK_SAFE
            else:
                try:
                    # Prepare clean feature input strictly using available features
                    features = self._prepare_ml_features(feature_record, ctx)
                    ml_res = self.model_manager.predict(features)

                    # Validate model output prediction
                    if (
                        not isinstance(ml_res.predicted_difficulty, str)
                        or ml_res.predicted_difficulty.strip().lower() not in VALID_DIFFICULTY_LEVELS
                    ):
                        raise ValueError(
                            f"Model returned invalid predicted difficulty: '{ml_res.predicted_difficulty}'"
                        )

                    raw_model_prediction = ml_res.predicted_difficulty.strip().lower()
                    model_confidence = ml_res.confidence
                    feature_snapshot = ml_res.feature_snapshot

                    # Check confidence threshold (0.60)
                    if ml_res.meets_confidence_threshold:
                        # Level 4: ML Adaptive
                        candidate_diff = raw_model_prediction
                        candidate_source = DecisionSource.ML_ADAPTIVE
                    else:
                        # Level 5: Low-confidence fallback
                        candidate_diff, fallback_reason = ColdStartRouter.evaluate_safe_fallback(
                            challenge_type=challenge_type,
                            baseline_difficulty=ctx.previous_difficulty,
                            recent_success_rate=eff_success_rate,
                            recent_avg_duration_seconds=eff_duration,
                            has_recent_failure=eff_has_failure,
                            current_session_snooze_count=ctx.current_session_snooze_count,
                            trigger_reason=f"low model confidence ({ml_res.confidence:.2f} < {self.model_manager.confidence_threshold})",
                        )
                        candidate_source = DecisionSource.FALLBACK_SAFE

                except Exception as exc:
                    # Level 6: Model unavailable / inference exception fallback
                    exc_type = type(exc).__name__
                    candidate_diff, fallback_reason = ColdStartRouter.evaluate_safe_fallback(
                        challenge_type=challenge_type,
                        baseline_difficulty=ctx.previous_difficulty,
                        recent_success_rate=eff_success_rate,
                        recent_avg_duration_seconds=eff_duration,
                        has_recent_failure=eff_has_failure,
                        current_session_snooze_count=ctx.current_session_snooze_count,
                        trigger_reason=f"model failure ({exc_type}: {str(exc)})",
                    )
                    candidate_source = DecisionSource.FALLBACK_SAFE
                    feature_snapshot = {
                        "ml_error_type": exc_type,
                        "ml_error_detail": str(exc),
                    }

        # F. Apply safety guardrails to adaptive candidate
        guardrail_res = SafetyGuardrails.apply_guardrails(
            candidate_difficulty=candidate_diff,
            previous_difficulty=ctx.previous_difficulty,
            current_session_snooze_count=ctx.current_session_snooze_count,
        )

        final_difficulty = guardrail_res.final_difficulty
        guardrail_applied = guardrail_res.guardrail_applied
        guardrail_reason = guardrail_res.guardrail_reason

        if guardrail_applied:
            final_decision_source = DecisionSource.GUARDRAIL_CLAMPED.value
        else:
            final_decision_source = candidate_source.value

        # G. Return complete PersonalizationDecision
        return PersonalizationDecision(
            recommended_difficulty=final_difficulty,
            challenge_type=challenge_type,
            decision_source=final_decision_source,
            model_confidence=model_confidence,
            raw_model_prediction=raw_model_prediction,
            guardrail_applied=guardrail_applied,
            guardrail_reason=guardrail_reason,
            feature_snapshot=feature_snapshot,
        )

    @staticmethod
    def _resolve_stage_1_telemetry(
        feature_record: Optional[Union[ChallengeFeatureRecord, Dict[str, Any]]],
        recent_success_rate: Optional[float],
        recent_avg_duration_seconds: Optional[float],
        has_recent_failure: bool,
    ) -> Tuple[Optional[float], Optional[float], bool]:
        """Extract available telemetry for Stage 1 contextual rules without fabricating values."""
        eff_success = recent_success_rate
        eff_duration = recent_avg_duration_seconds
        eff_failure = has_recent_failure

        if feature_record is not None:
            if isinstance(feature_record, ChallengeFeatureRecord):
                feat_dict = feature_record.to_dict(
                    include_targets=False, include_metadata=False
                )
            elif isinstance(feature_record, dict):
                feat_dict = feature_record
            else:
                feat_dict = {}

            if eff_success is None and "user_recent_challenge_success_rate" in feat_dict:
                eff_success = feat_dict["user_recent_challenge_success_rate"]

            if eff_duration is None:
                if (
                    feat_dict.get("challenge_type_avg_completion_time") is not None
                    and feat_dict["challenge_type_avg_completion_time"] > 0
                ):
                    eff_duration = feat_dict["challenge_type_avg_completion_time"]
                elif (
                    feat_dict.get("user_avg_completion_time_seconds") is not None
                    and feat_dict["user_avg_completion_time_seconds"] > 0
                ):
                    eff_duration = feat_dict["user_avg_completion_time_seconds"]

        return eff_success, eff_duration, eff_failure

    @staticmethod
    def _prepare_ml_features(
        feature_record: Union[ChallengeFeatureRecord, Dict[str, Any]],
        context: PersonalizationContext,
    ) -> Dict[str, Any]:
        """Prepare feature dict ensuring strictly approved features and immutable context."""
        if isinstance(feature_record, ChallengeFeatureRecord):
            raw_dict = feature_record.to_dict(
                include_targets=False, include_metadata=False
            )
        elif isinstance(feature_record, dict):
            raw_dict = dict(feature_record)
        else:
            raise ValueError(
                f"feature_record must be ChallengeFeatureRecord or dict, got {type(feature_record).__name__}"
            )

        # Enforce context immutability
        raw_dict["selected_challenge_type"] = context.challenge_type
        raw_dict["current_session_snooze_count"] = context.current_session_snooze_count

        # Prevent leakage of preferences and post-challenge targets
        leakage_keys = [
            "user_selected_difficulty",
            "is_adaptive_preference",
            "target_is_successful",
            "target_duration_seconds",
            "target_verification_score",
            "target_attempt_number",
            "user_id",
            "wake_session_id",
            "challenge_attempt_id",
            "alarm_id",
            "timestamp",
        ]
        for key in leakage_keys:
            raw_dict.pop(key, None)

        return raw_dict
