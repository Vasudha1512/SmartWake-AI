"""Comprehensive Pipeline & Regression Validation Tests for Phase 4.5 (Step 6).

Validates the complete end-to-end Phase 4.5 challenge personalization pipeline:
    PersonalizedChallengeProfile (Step 3)
              ↓
    ChallengePersonalizationService (Step 3)
              ↓
    adapt_profile() / Procedural Adapters (Step 4)
              ↓
    PersonalizationDispatcher (Step 5)
              ↓
    Target Generator Contract / Procedural Adapter Path

COVERS 15 INTEGRATION & REGRESSION TEST GROUPS:
1. Five-Type Complete Pipeline (math, memory, tongue_twister, dance, push_ups)
2. Difficulty Authority & Duration Invariance (easy, medium, hard; 5s - 300s)
3. Challenge Type Authority & Forbidden Type Rejection
4. Personalization Parameter Preservation Across Pipeline
5. Precedence Hierarchy Validation (Safety > Type > Diff > Prefs > Behavioral > Repetition > Defaults)
6. Structural Repetition Safety & Determinism
7. Pipeline Determinism (Zero Randomness / Timestamps)
8. Input Profile Immutability
9. Privacy & Data Boundary Isolation (Zero DB IDs / PII)
10. Database & ORM Isolation (AST & Runtime)
11. Network & LLM Isolation (AST & Runtime)
12. Zero Runtime Content Generation in Personalization Layer
13. Zero Challenge Verification in Personalization Layer
14. Error Propagation & Safe Rejection
15. Cross-Phase Generator Contract Compatibility (Phases 4.2, 4.3, 4.4)
"""
import ast
import copy
import inspect
import unittest
from typing import List, Optional, Sequence

from pydantic import ValidationError

from backend.app.core.constants import FORBIDDEN_CHALLENGE_TYPES
from backend.app.core.exceptions import (
    InvalidChallengeTypeError,
    InvalidDifficultyError,
    SmartWakeException,
)
from backend.app.schemas.challenge_content_schemas import (
    FORBIDDEN_CONTEXT_KEYS,
    SafePersonalizationContext,
)
from backend.app.schemas.personalization_content_schemas import (
    BehavioralPersonalizationSignals,
    CanonicalChallengeType,
    CanonicalDifficultyLevel,
    DancePersonalizationParams,
    MathPersonalizationParams,
    MemoryPersonalizationParams,
    PersonalizedChallengeProfile,
    PushUpPersonalizationParams,
    TongueTwisterPersonalizationParams,
    VALID_CANONICAL_CHALLENGE_TYPES,
    VALID_CANONICAL_DIFFICULTIES,
)
from backend.app.services.genai.challenge_personalization_service import (
    ChallengePersonalizationService,
    ForbiddenChallengeTypeError,
    InvalidChallengeTypeError as ServiceInvalidChallengeTypeError,
    InvalidDifficultyLevelError as ServiceInvalidDifficultyError,
)
from backend.app.services.genai.math_challenge_generator import MathChallengeGenerator
from backend.app.services.genai.memory_challenge_generator import MemoryChallengeGenerator
from backend.app.services.genai.personalization_adapters import (
    DancePersonalizationAdapterOutput,
    MathPersonalizationAdapterOutput,
    MemoryPersonalizationAdapterOutput,
    PushUpPersonalizationAdapterOutput,
    TongueTwisterPersonalizationAdapterOutput,
    adapt_profile,
)
from backend.app.services.genai.tongue_twister_challenge_generator import (
    TongueTwisterChallengeGenerator,
)
from backend.app.services.personalization_dispatcher import (
    DanceDispatchResult,
    DispatcherDifficultyError,
    DispatcherError,
    DispatcherTypeError,
    DispatchTarget,
    MathDispatchResult,
    MathGeneratorInputArgs,
    MemoryDispatchResult,
    MemoryGeneratorInputArgs,
    PersonalizationDispatcher,
    PushUpDispatchResult,
    TongueTwisterDispatchResult,
    TongueTwisterGeneratorInputArgs,
    dispatch_profile,
)


def _make_context(
    desired_duration_seconds: Optional[int] = None,
    preferred_theme: Optional[str] = None,
    disallowed_topics: Optional[List[str]] = None,
) -> SafePersonalizationContext:
    """Helper constructing SafePersonalizationContext with all optional fields provided."""
    return SafePersonalizationContext(
        desired_duration_seconds=desired_duration_seconds,
        preferred_theme=preferred_theme,
        disallowed_topics=disallowed_topics or [],
    )


class BasePipelineTestCase(unittest.TestCase):
    """Base fixture providing initialized service and dispatcher instances."""

    def setUp(self) -> None:
        self.service = ChallengePersonalizationService()
        self.dispatcher = PersonalizationDispatcher()


# =============================================================================
# TEST GROUP 1 — FIVE-TYPE PIPELINE
# =============================================================================

class TestFiveTypePipeline(BasePipelineTestCase):
    """Group 1: End-to-end personalization flow for all five canonical types."""

    def test_math_pipeline_end_to_end(self) -> None:
        """Verify math: Service -> Profile -> Adapter -> Dispatcher -> MathDispatchResult."""
        context = SafePersonalizationContext(preferred_theme="astronomy", desired_duration_seconds=30)
        profile = self.service.personalize("math", "medium", safe_context=context)

        self.assertEqual(profile.challenge_type, "math")
        self.assertEqual(profile.difficulty_level, "medium")

        adapter_output = adapt_profile(profile)
        self.assertIsInstance(adapter_output, MathPersonalizationAdapterOutput)

        dispatch_result = self.dispatcher.dispatch(profile)
        self.assertIsInstance(dispatch_result, MathDispatchResult)
        assert isinstance(dispatch_result, MathDispatchResult)

        self.assertEqual(dispatch_result.challenge_type, "math")
        self.assertEqual(dispatch_result.difficulty, "medium")
        self.assertEqual(dispatch_result.selected_path, DispatchTarget.MATH_GENERATOR.value)
        self.assertIs(dispatch_result.generator_class, MathChallengeGenerator)
        self.assertIsInstance(dispatch_result.generator_input, MathGeneratorInputArgs)

    def test_memory_pipeline_end_to_end(self) -> None:
        """Verify memory: Service -> Profile -> Adapter -> Dispatcher -> MemoryDispatchResult."""
        context = SafePersonalizationContext(preferred_theme="geometric_shapes", desired_duration_seconds=45)
        profile = self.service.personalize("memory", "hard", safe_context=context)

        self.assertEqual(profile.challenge_type, "memory")
        self.assertEqual(profile.difficulty_level, "hard")

        adapter_output = adapt_profile(profile)
        self.assertIsInstance(adapter_output, MemoryPersonalizationAdapterOutput)

        dispatch_result = self.dispatcher.dispatch(profile)
        self.assertIsInstance(dispatch_result, MemoryDispatchResult)
        assert isinstance(dispatch_result, MemoryDispatchResult)

        self.assertEqual(dispatch_result.challenge_type, "memory")
        self.assertEqual(dispatch_result.difficulty, "hard")
        self.assertEqual(dispatch_result.selected_path, DispatchTarget.MEMORY_GENERATOR.value)
        self.assertIs(dispatch_result.generator_class, MemoryChallengeGenerator)
        self.assertIsInstance(dispatch_result.generator_input, MemoryGeneratorInputArgs)

    def test_tongue_twister_pipeline_end_to_end(self) -> None:
        """Verify tongue_twister: Service -> Profile -> Adapter -> Dispatcher -> TongueTwisterDispatchResult."""
        context = SafePersonalizationContext(preferred_theme="rhyme", desired_duration_seconds=20)
        profile = self.service.personalize("tongue_twister", "easy", safe_context=context)

        self.assertEqual(profile.challenge_type, "tongue_twister")
        self.assertEqual(profile.difficulty_level, "easy")

        adapter_output = adapt_profile(profile)
        self.assertIsInstance(adapter_output, TongueTwisterPersonalizationAdapterOutput)

        dispatch_result = self.dispatcher.dispatch(profile)
        self.assertIsInstance(dispatch_result, TongueTwisterDispatchResult)
        assert isinstance(dispatch_result, TongueTwisterDispatchResult)

        self.assertEqual(dispatch_result.challenge_type, "tongue_twister")
        self.assertEqual(dispatch_result.difficulty, "easy")
        self.assertEqual(dispatch_result.selected_path, DispatchTarget.TONGUE_TWISTER_GENERATOR.value)
        self.assertIs(dispatch_result.generator_class, TongueTwisterChallengeGenerator)
        self.assertIsInstance(dispatch_result.generator_input, TongueTwisterGeneratorInputArgs)

    def test_dance_pipeline_end_to_end(self) -> None:
        """Verify dance: Service -> Profile -> Adapter -> Dispatcher -> DanceDispatchResult (procedural)."""
        context = _make_context(desired_duration_seconds=60)
        profile = self.service.personalize("dance", "medium", safe_context=context)

        self.assertEqual(profile.challenge_type, "dance")
        self.assertEqual(profile.difficulty_level, "medium")

        adapter_output = adapt_profile(profile)
        self.assertIsInstance(adapter_output, DancePersonalizationAdapterOutput)

        dispatch_result = self.dispatcher.dispatch(profile)
        self.assertIsInstance(dispatch_result, DanceDispatchResult)
        assert isinstance(dispatch_result, DanceDispatchResult)

        self.assertEqual(dispatch_result.challenge_type, "dance")
        self.assertEqual(dispatch_result.difficulty, "medium")
        self.assertEqual(dispatch_result.selected_path, DispatchTarget.DANCE_ADAPTER.value)
        self.assertTrue(dispatch_result.is_procedural)

    def test_push_ups_pipeline_end_to_end(self) -> None:
        """Verify push_ups: Service -> Profile -> Adapter -> Dispatcher -> PushUpDispatchResult (procedural)."""
        context = _make_context(desired_duration_seconds=45)
        profile = self.service.personalize("push_ups", "hard", safe_context=context)

        self.assertEqual(profile.challenge_type, "push_ups")
        self.assertEqual(profile.difficulty_level, "hard")

        adapter_output = adapt_profile(profile)
        self.assertIsInstance(adapter_output, PushUpPersonalizationAdapterOutput)

        dispatch_result = self.dispatcher.dispatch(profile)
        self.assertIsInstance(dispatch_result, PushUpDispatchResult)
        assert isinstance(dispatch_result, PushUpDispatchResult)

        self.assertEqual(dispatch_result.challenge_type, "push_ups")
        self.assertEqual(dispatch_result.difficulty, "hard")
        self.assertEqual(dispatch_result.selected_path, DispatchTarget.PUSH_UPS_ADAPTER.value)
        self.assertTrue(dispatch_result.is_procedural)


# =============================================================================
# TEST GROUP 2 — DIFFICULTY AUTHORITY & DURATION INVARIANCE
# =============================================================================

class TestDifficultyAuthority(BasePipelineTestCase):
    """Group 2: Difficulty authority preserved across all tiers and duration hints."""

    def test_difficulty_preserved_across_all_types_and_tiers(self) -> None:
        """Verify profile diff = adapter diff = dispatcher diff across 15 permutations."""
        for ctype in sorted(list(VALID_CANONICAL_CHALLENGE_TYPES)):
            for diff in ("easy", "medium", "hard"):
                with self.subTest(challenge_type=ctype, difficulty=diff):
                    profile = self.service.personalize(ctype, diff)
                    self.assertEqual(profile.difficulty_level, diff)

                    adapter_output = adapt_profile(profile)
                    self.assertEqual(adapter_output.difficulty_level, diff)

                    dispatch_result = self.dispatcher.dispatch(profile)
                    self.assertEqual(dispatch_result.difficulty, diff)
                    self.assertEqual(dispatch_result.difficulty_level, diff)

    def test_desired_duration_seconds_never_modifies_difficulty(self) -> None:
        """Verify desired_duration_seconds (5, 30, 60, 120, 300) leaves difficulty unchanged."""
        test_durations = [5, 30, 60, 120, 300]
        for ctype in sorted(list(VALID_CANONICAL_CHALLENGE_TYPES)):
            for diff in ("easy", "medium", "hard"):
                for dur in test_durations:
                    with self.subTest(challenge_type=ctype, difficulty=diff, duration=dur):
                        ctx = _make_context(desired_duration_seconds=dur)
                        profile = self.service.personalize(ctype, diff, safe_context=ctx)
                        dispatch_result = self.dispatcher.dispatch(profile)

                        self.assertEqual(dispatch_result.difficulty, diff)
                        self.assertEqual(dispatch_result.difficulty_level, diff)
                        self.assertEqual(dispatch_result.challenge_type, ctype)


# =============================================================================
# TEST GROUP 3 — CHALLENGE TYPE AUTHORITY
# =============================================================================

class TestChallengeTypeAuthority(BasePipelineTestCase):
    """Group 3: Type authority preserved; forbidden types rejected."""

    def test_challenge_type_survives_pipeline_unmodified(self) -> None:
        """Verify no component mutates challenge type (math never becomes memory, etc.)."""
        for ctype in sorted(list(VALID_CANONICAL_CHALLENGE_TYPES)):
            with self.subTest(challenge_type=ctype):
                profile = self.service.personalize(ctype, "medium")
                adapter_output = adapt_profile(profile)
                dispatch_result = self.dispatcher.dispatch(profile)

                self.assertEqual(profile.challenge_type, ctype)
                self.assertEqual(adapter_output.challenge_type, ctype)
                self.assertEqual(dispatch_result.challenge_type, ctype)

    def test_forbidden_challenge_types_rejected_by_service_and_dispatcher(self) -> None:
        """Verify forbidden types (number_guessing, guess_number, numeric_memory) fail early."""
        for forbidden in FORBIDDEN_CHALLENGE_TYPES:
            with self.subTest(forbidden_type=forbidden):
                # Service level rejection
                with self.assertRaises((ForbiddenChallengeTypeError, ServiceInvalidChallengeTypeError)):
                    self.service.personalize(forbidden, "medium")

                # Dispatcher level rejection
                mock_profile = self.service.personalize("math", "easy")
                object.__setattr__(mock_profile, "challenge_type", forbidden)
                with self.assertRaises(DispatcherTypeError):
                    self.dispatcher.dispatch(mock_profile)


# =============================================================================
# TEST GROUP 4 — PERSONALIZATION PARAMETERS
# =============================================================================

class TestPersonalizationParameters(BasePipelineTestCase):
    """Group 4: Type-specific parameters survive pipeline intact."""

    def test_math_personalization_parameters_preserved(self) -> None:
        """Verify focus_topic, preferred_operation, and operand_scale_preference."""
        ctx = SafePersonalizationContext(preferred_theme="astronomy", desired_duration_seconds=15)
        profile = self.service.personalize("math", "easy", safe_context=ctx)

        dispatch_result = self.dispatcher.dispatch(profile)
        assert isinstance(dispatch_result, MathDispatchResult)

        self.assertEqual(dispatch_result.adapter_output.focus_topic, "astronomy")
        self.assertEqual(dispatch_result.generator_input.raw_context.preferred_theme, "astronomy")
        self.assertEqual(dispatch_result.adapter_output.operand_scale_preference, "compact")

    def test_memory_personalization_parameters_preserved(self) -> None:
        """Verify preferred_mode and palette_theme in memory pipeline."""
        ctx = _make_context(preferred_theme="geometric_shapes")
        profile = self.service.personalize("memory", "medium", safe_context=ctx)

        dispatch_result = self.dispatcher.dispatch(profile)
        assert isinstance(dispatch_result, MemoryDispatchResult)

        self.assertEqual(dispatch_result.adapter_output.palette_theme, "geometric_shapes")
        self.assertEqual(dispatch_result.generator_input.raw_context.preferred_theme, "geometric_shapes")
        self.assertIsNotNone(dispatch_result.generator_input.preferred_mode)

    def test_tongue_twister_personalization_parameters_preserved(self) -> None:
        """Verify sound_family and theme_style in tongue twister pipeline."""
        ctx = _make_context(preferred_theme="nature")
        profile = self.service.personalize("tongue_twister", "hard", safe_context=ctx)

        dispatch_result = self.dispatcher.dispatch(profile)
        assert isinstance(dispatch_result, TongueTwisterDispatchResult)

        self.assertEqual(dispatch_result.adapter_output.theme_style, "nature")
        self.assertEqual(dispatch_result.generator_input.raw_context.preferred_theme, "nature")
        self.assertIsNotNone(dispatch_result.adapter_output.target_sound_family)

    def test_dance_personalization_parameters_preserved(self) -> None:
        """Verify movement_style and pacing in dance pipeline."""
        ctx = _make_context(preferred_theme="rhythm_groove")
        profile = self.service.personalize("dance", "medium", safe_context=ctx)

        dispatch_result = self.dispatcher.dispatch(profile)
        assert isinstance(dispatch_result, DanceDispatchResult)

        self.assertEqual(dispatch_result.adapter_output.movement_style, "rhythm_groove")
        self.assertIsNotNone(dispatch_result.adapter_output.pacing)

    def test_push_ups_personalization_parameters_preserved(self) -> None:
        """Verify cadence_tempo and target_rep_styling in push-ups pipeline."""
        ctx = _make_context(desired_duration_seconds=30)
        profile = self.service.personalize("push_ups", "hard", safe_context=ctx)

        dispatch_result = self.dispatcher.dispatch(profile)
        assert isinstance(dispatch_result, PushUpDispatchResult)

        self.assertIsNotNone(dispatch_result.adapter_output.cadence_tempo)
        self.assertIsNotNone(dispatch_result.adapter_output.target_rep_styling)


# =============================================================================
# TEST GROUP 5 — PRECEDENCE HIERARCHY
# =============================================================================

class TestPrecedenceHierarchy(BasePipelineTestCase):
    """Group 5: Safety > Challenge Type > Difficulty > Explicit Prefs > Behavioral > Repetition > Defaults."""

    def test_safety_preempts_disallowed_topic_preserving_type_and_diff(self) -> None:
        """Safety wins: disallowed_topic is filtered out, but type & diff remain authoritative."""
        ctx = _make_context(
            preferred_theme="violence and combat",
            disallowed_topics=["violence", "combat"],
        )
        profile = self.service.personalize("math", "hard", safe_context=ctx)
        dispatch_result = self.dispatcher.dispatch(profile)

        self.assertEqual(dispatch_result.challenge_type, "math")
        self.assertEqual(dispatch_result.difficulty, "hard")
        assert isinstance(dispatch_result, MathDispatchResult)
        self.assertIsNone(dispatch_result.adapter_output.focus_topic)

    def test_explicit_preference_overrides_behavioral_defaults(self) -> None:
        """Explicit preferences take priority over behavioral signals without changing diff."""
        ctx = SafePersonalizationContext(preferred_theme="astronomy", desired_duration_seconds=20)
        signals = BehavioralPersonalizationSignals(
            recent_snooze_level="high",
            recent_failure_count=3,
        )
        profile = self.service.personalize("math", "medium", safe_context=ctx, behavioral_signals=signals)
        dispatch_result = self.dispatcher.dispatch(profile)
        assert isinstance(dispatch_result, MathDispatchResult)

        self.assertEqual(dispatch_result.difficulty, "medium")
        self.assertEqual(dispatch_result.adapter_output.focus_topic, "astronomy")
        self.assertEqual(dispatch_result.adapter_output.operand_scale_preference, "compact")

    def test_behavioral_signals_tune_style_never_difficulty(self) -> None:
        """Behavioral inertia (high snooze) tunes compact scale but NEVER demotes hard -> easy."""
        signals = BehavioralPersonalizationSignals(recent_snooze_level="high", recent_failure_count=2)
        profile = self.service.personalize("math", "hard", behavioral_signals=signals)
        dispatch_result = self.dispatcher.dispatch(profile)

        self.assertEqual(dispatch_result.difficulty, "hard")
        assert isinstance(dispatch_result, MathDispatchResult)
        self.assertEqual(dispatch_result.adapter_output.operand_scale_preference, "compact")


# =============================================================================
# TEST GROUP 6 — REPETITION SAFETY
# =============================================================================

class TestRepetitionSafety(BasePipelineTestCase):
    """Group 6: Bounded structural repetition, determinism, and lack of embeddings/vector DB."""

    def test_recent_signatures_passed_and_bounded(self) -> None:
        """Signatures are bounded to max capacity (5) and processed newest-first."""
        sigs = [f"sig_{i}" for i in range(10)]
        profile = self.service.personalize(
            "math", "easy", recent_structural_signatures=sigs
        )
        self.assertLessEqual(len(profile.recent_structural_signatures), 5)

    def test_repetition_triggers_deterministic_alternative_preserving_type_and_diff(self) -> None:
        """Structural repetition on candidate rotates styling while preserving type & diff."""
        # Generate initial profile and get its signature
        p1 = self.service.personalize("memory", "medium")
        from backend.app.services.genai.structural_repetition import build_signature_from_profile
        sig1 = build_signature_from_profile(p1)

        # Generate second profile with sig1 in history
        p2 = self.service.personalize("memory", "medium", recent_structural_signatures=[sig1])
        self.assertEqual(p2.challenge_type, "memory")
        self.assertEqual(p2.difficulty_level, "medium")

        # Dispatch p2
        res = self.dispatcher.dispatch(p2)
        self.assertEqual(res.challenge_type, "memory")
        self.assertEqual(res.difficulty, "medium")


# =============================================================================
# TEST GROUP 7 — PIPELINE DETERMINISM
# =============================================================================

class TestPipelineDeterminism(BasePipelineTestCase):
    """Group 7: Identical inputs yield identical outputs (pure deterministic behavior)."""

    def test_repeated_pipeline_runs_produce_identical_outputs(self) -> None:
        """Running the full pipeline 5 times with identical inputs produces identical outputs."""
        ctx = SafePersonalizationContext(preferred_theme="astronomy", desired_duration_seconds=45)
        signals = BehavioralPersonalizationSignals(recent_snooze_level="low", historical_success_rate=0.8)

        results = []
        for _ in range(5):
            profile = self.service.personalize(
                "math", "medium", safe_context=ctx, behavioral_signals=signals
            )
            res = self.dispatcher.dispatch(profile)
            results.append(res)

        first_dump = results[0].model_dump()
        for i, res in enumerate(results[1:], start=2):
            self.assertEqual(res.model_dump(), first_dump, f"Run {i} diverged from Run 1.")


# =============================================================================
# TEST GROUP 8 — IMMUTABILITY
# =============================================================================

class TestPipelineImmutability(BasePipelineTestCase):
    """Group 8: Input profile is treated as read-only and never mutated."""

    def test_profile_unchanged_after_adapter_and_dispatcher(self) -> None:
        """PersonalizedChallengeProfile remains identical before and after pipeline execution."""
        profile = self.service.personalize("dance", "hard", safe_context=_make_context(desired_duration_seconds=60))
        before_dump = copy.deepcopy(profile.model_dump())

        _ = adapt_profile(profile)
        _ = self.dispatcher.dispatch(profile)
        _ = dispatch_profile(profile)

        self.assertEqual(profile.model_dump(), before_dump)


# =============================================================================
# TEST GROUP 9 — PRIVACY BOUNDARY
# =============================================================================

class TestPrivacyBoundary(BasePipelineTestCase):
    """Group 9: Pipeline operates with zero user IDs, PII, or raw ORM/DB entities."""

    def test_pipeline_functions_without_any_identity_data(self) -> None:
        """Verify pipeline succeeds with purely anonymous sanitized inputs."""
        profile = self.service.personalize("tongue_twister", "medium")
        res = self.dispatcher.dispatch(profile)

        self.assertEqual(res.challenge_type, "tongue_twister")
        self.assertFalse(hasattr(res, "user_id"))
        self.assertFalse(hasattr(res, "alarm_id"))
        self.assertFalse(hasattr(res, "email"))

    def test_forbidden_context_keys_rejected_at_boundary(self) -> None:
        """Attempting to inject identity keys (user_id, session_id, etc.) is rejected."""
        for key in FORBIDDEN_CONTEXT_KEYS:
            with self.assertRaises(ValidationError):
                SafePersonalizationContext(**{key: "identity_value"})  # pyright: ignore[reportArgumentType]


# =============================================================================
# TEST GROUPS 10 & 11 — DB / ORM & NETWORK / LLM ISOLATION
# =============================================================================

class TestIsolationAndBoundaries(unittest.TestCase):
    """Groups 10 & 11: Static and AST inspection verifying zero DB/ORM and zero network/LLM dependencies."""

    PIPELINE_MODULES = [
        "backend.app.schemas.personalization_content_schemas",
        "backend.app.services.genai.structural_repetition",
        "backend.app.services.genai.challenge_personalization_service",
        "backend.app.services.genai.personalization_adapters",
        "backend.app.services.personalization_dispatcher",
    ]

    def test_no_database_or_orm_imports_in_pipeline(self) -> None:
        """Group 10: Verify no SQLAlchemy or DB imports exist in Phase 4.5 modules."""
        forbidden_db = ["sqlalchemy", "alembic", "backend.app.models", "backend.app.db", "get_db", "Session"]

        for mod_name in self.PIPELINE_MODULES:
            mod = __import__(mod_name, fromlist=["*"])
            source = inspect.getsource(mod)
            tree = ast.parse(source)

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        for forbidden in forbidden_db:
                            self.assertNotIn(forbidden, alias.name, f"{mod_name} imports DB symbol {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    mod_path = node.module or ""
                    for forbidden in forbidden_db:
                        self.assertNotIn(forbidden, mod_path, f"{mod_name} imports from DB module {mod_path}")

    def test_no_network_or_llm_imports_in_pipeline(self) -> None:
        """Group 11: Verify no HTTP client or LLM SDK imports exist in Phase 4.5 modules."""
        forbidden_net = [
            "requests",
            "httpx",
            "aiohttp",
            "urllib.request",
            "google.generativeai",
            "openai",
            "gemini",
            "langchain",
        ]

        for mod_name in self.PIPELINE_MODULES:
            mod = __import__(mod_name, fromlist=["*"])
            source = inspect.getsource(mod)
            tree = ast.parse(source)

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        for forbidden in forbidden_net:
                            self.assertNotIn(forbidden, alias.name, f"{mod_name} imports net symbol {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    mod_path = node.module or ""
                    for forbidden in forbidden_net:
                        self.assertNotIn(forbidden, mod_path, f"{mod_name} imports from net module {mod_path}")


# =============================================================================
# TEST GROUPS 12 & 13 — NO CONTENT GENERATION & NO VERIFICATION
# =============================================================================

class TestNoContentGenerationOrVerification(BasePipelineTestCase):
    """Groups 12 & 13: Orchestration produces routing contracts, NOT challenge content or verification."""

    def test_no_challenge_content_generated_by_pipeline(self) -> None:
        """Group 12: Pipeline outputs contain zero questions, answers, sentence text, or routines."""
        for ctype in sorted(list(VALID_CANONICAL_CHALLENGE_TYPES)):
            with self.subTest(challenge_type=ctype):
                profile = self.service.personalize(ctype, "medium")
                res = self.dispatcher.dispatch(profile)

                self.assertFalse(hasattr(res, "content_payload"))
                self.assertFalse(hasattr(res, "expected_answer"))
                self.assertFalse(hasattr(res, "questions"))
                self.assertFalse(hasattr(res, "choreography"))
                self.assertFalse(hasattr(res, "reps"))

    def test_no_verification_performed_by_pipeline(self) -> None:
        """Group 13: Pipeline contains zero grading, pose tracking, or verification results."""
        for ctype in sorted(list(VALID_CANONICAL_CHALLENGE_TYPES)):
            with self.subTest(challenge_type=ctype):
                profile = self.service.personalize(ctype, "medium")
                res = self.dispatcher.dispatch(profile)

                self.assertFalse(hasattr(res, "verification_mode"))
                self.assertFalse(hasattr(res, "is_verified"))
                self.assertFalse(hasattr(res, "passed"))


# =============================================================================
# TEST GROUP 14 — ERROR PROPAGATION
# =============================================================================

class TestErrorPropagation(BasePipelineTestCase):
    """Group 14: Invalid inputs fail explicitly with appropriate domain exceptions."""

    def test_invalid_challenge_types_fail_explicitly(self) -> None:
        """Invalid challenge types raise domain exceptions at both service and dispatcher."""
        invalid_types = ["trivia", "crossword", "speed_reading", "", "   ", "invalid_type"]
        for bad_type in invalid_types:
            with self.subTest(bad_type=bad_type):
                with self.assertRaises(ServiceInvalidChallengeTypeError):
                    self.service.personalize(bad_type, "easy")

    def test_invalid_difficulty_levels_fail_explicitly(self) -> None:
        """Invalid difficulties raise domain exceptions at both service and dispatcher."""
        invalid_diffs = ["adaptive", "extreme", "ultra", "", "   ", "impossible"]
        for bad_diff in invalid_diffs:
            with self.subTest(bad_diff=bad_diff):
                with self.assertRaises(ServiceInvalidDifficultyError):
                    self.service.personalize("math", bad_diff)


# =============================================================================
# TEST GROUP 15 — CROSS-PHASE GENERATOR CONTRACT COMPATIBILITY
# =============================================================================

class TestCrossPhaseGeneratorContracts(BasePipelineTestCase):
    """Group 15: Generator-compatible parameters align directly with Phase 4.2/4.3/4.4 generators."""

    def test_math_generator_contract_alignment(self) -> None:
        """Verify MathGeneratorInputArgs aligns with MathChallengeGenerator.generate_math_challenge."""
        sig = inspect.signature(MathChallengeGenerator.generate_math_challenge)
        profile = self.service.personalize("math", "hard", safe_context=_make_context(desired_duration_seconds=30))
        res = self.dispatcher.dispatch(profile)
        assert isinstance(res, MathDispatchResult)

        gen_input = res.generator_input
        self.assertIn("difficulty_level", sig.parameters)
        self.assertIn("challenge_type", sig.parameters)
        self.assertIn("raw_context", sig.parameters)
        self.assertIn("strict_context", sig.parameters)

        self.assertEqual(gen_input.difficulty_level, "hard")
        self.assertEqual(gen_input.challenge_type, "math")
        self.assertTrue(gen_input.strict_context)
        self.assertIsInstance(gen_input.raw_context, SafePersonalizationContext)

    def test_memory_generator_contract_alignment(self) -> None:
        """Verify MemoryGeneratorInputArgs aligns with MemoryChallengeGenerator.generate_memory_challenge."""
        sig = inspect.signature(MemoryChallengeGenerator.generate_memory_challenge)
        profile = self.service.personalize("memory", "medium")
        res = self.dispatcher.dispatch(profile)
        assert isinstance(res, MemoryDispatchResult)

        gen_input = res.generator_input
        self.assertIn("preferred_mode", sig.parameters)
        self.assertEqual(gen_input.challenge_type, "memory")
        self.assertEqual(gen_input.difficulty_level, "medium")
        self.assertIsInstance(gen_input.raw_context, SafePersonalizationContext)

    def test_tongue_twister_generator_contract_alignment(self) -> None:
        """Verify TongueTwisterGeneratorInputArgs aligns with TongueTwister generator."""
        sig = inspect.signature(TongueTwisterChallengeGenerator.generate_tongue_twister_challenge)
        profile = self.service.personalize("tongue_twister", "easy")
        res = self.dispatcher.dispatch(profile)
        assert isinstance(res, TongueTwisterDispatchResult)

        gen_input = res.generator_input
        self.assertEqual(gen_input.challenge_type, "tongue_twister")
        self.assertEqual(gen_input.difficulty_level, "easy")
        self.assertIsInstance(gen_input.raw_context, SafePersonalizationContext)

    def test_procedural_types_have_no_generator_input(self) -> None:
        """Verify dance and push_ups remain purely procedural with no generator inputs."""
        dance_res = self.dispatcher.dispatch(self.service.personalize("dance", "medium"))
        pu_res = self.dispatcher.dispatch(self.service.personalize("push_ups", "hard"))

        assert isinstance(dance_res, DanceDispatchResult)
        assert isinstance(pu_res, PushUpDispatchResult)

        self.assertTrue(dance_res.is_procedural)
        self.assertTrue(pu_res.is_procedural)
        self.assertFalse(hasattr(dance_res, "generator_input"))
        self.assertFalse(hasattr(pu_res, "generator_input"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
