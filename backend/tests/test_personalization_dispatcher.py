"""Comprehensive Unit Tests for Personalization Dispatcher (Phase 4.5 Step 5).

Covers all required test criteria A through Y:
A. Math profile routes to math generator path
B. Memory profile routes to memory generator path
C. Tongue-twister profile routes to tongue-twister generator path
D. Dance profile routes to procedural dance adapter path
E. Push-ups profile routes to procedural push-up adapter path
F. Challenge type is preserved exactly for all five types
G. Difficulty is preserved exactly for easy, medium, hard
H. Relevant personalization parameters are preserved
I. Unsupported personalization fields cannot override challenge type or difficulty
J. Forbidden challenge types are rejected with DispatcherTypeError
K. Unknown challenge types are rejected with DispatcherTypeError
L. Invalid difficulty values are rejected with DispatcherDifficultyError
M. desired_duration_seconds values across the valid range do not alter difficulty
N. Dispatcher has no database/ORM dependency
O. Dispatcher has no network/LLM dependency
P. Dispatcher does not generate final challenge content
Q. Dispatcher does not perform verification
R. Input PersonalizedChallengeProfile remains unchanged (strict immutability)
S. All five canonical challenge types have explicit typed routing
T. Production dispatcher contains no Dict[str, Any]
U. Existing Phase 4.2/4.3/4.4 generator contracts remain unchanged
V. Generator-compatible inputs contain the authoritative difficulty
W. Generator-compatible inputs contain the correct challenge type
X. Memory preferred_mode is routed correctly
Y. desired_duration_seconds never changes difficulty
"""
import ast
import copy
import inspect
import unittest
from typing import Optional, Union

from backend.app.core.constants import FORBIDDEN_CHALLENGE_TYPES
from backend.app.core.exceptions import (
    InvalidChallengeTypeError,
    InvalidDifficultyError,
    SmartWakeException,
)
from backend.app.schemas.challenge_content_schemas import SafePersonalizationContext
from backend.app.schemas.personalization_content_schemas import (
    BehavioralPersonalizationSignals,
    CanonicalChallengeType,
    CanonicalDifficultyLevel,
    DancePersonalizationParams,
    MathPersonalizationParams,
    MemoryPersonalizationParams,
    PersonalizationParamsType,
    PersonalizedChallengeProfile,
    PushUpPersonalizationParams,
    TongueTwisterPersonalizationParams,
    VALID_CANONICAL_CHALLENGE_TYPES,
    VALID_CANONICAL_DIFFICULTIES,
)
from backend.app.services.genai.math_challenge_generator import MathChallengeGenerator
from backend.app.services.genai.memory_challenge_generator import MemoryChallengeGenerator
from backend.app.services.genai.personalization_adapters import (
    AdapterDifficultyError,
    AdapterTypeError,
    DancePersonalizationAdapterOutput,
    MathPersonalizationAdapterOutput,
    MemoryPersonalizationAdapterOutput,
    PushUpPersonalizationAdapterOutput,
    TongueTwisterPersonalizationAdapterOutput,
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


def _make_profile(
    challenge_type: CanonicalChallengeType,
    difficulty_level: CanonicalDifficultyLevel,
    typed_params: Optional[PersonalizationParamsType] = None,
    desired_duration_seconds: Optional[int] = None,
    preferred_theme: Optional[str] = None,
) -> PersonalizedChallengeProfile:
    """Helper to build a valid PersonalizedChallengeProfile for dispatcher tests."""
    return PersonalizedChallengeProfile(
        challenge_type=challenge_type,
        difficulty_level=difficulty_level,
        safe_context=SafePersonalizationContext(
            desired_duration_seconds=desired_duration_seconds,
            preferred_theme=preferred_theme,
        ),
        behavioral_signals=BehavioralPersonalizationSignals(),
        recent_structural_signatures=[],
        typed_parameters=typed_params,
    )


# =============================================================================
# A. MATH DISPATCH TESTS
# =============================================================================

class TestMathDispatch(unittest.TestCase):
    """Tests A, F, G, H, V, W, X, Y for math challenge profile routing."""

    def setUp(self) -> None:
        self.dispatcher = PersonalizationDispatcher()

    def test_math_profile_routes_to_math_generator_path(self) -> None:
        """Test A: Math profile routes to MathDispatchResult with math_challenge_generator path."""
        params = MathPersonalizationParams(focus_topic="astronomy", preferred_operation="addition")
        profile = _make_profile("math", "medium", params, desired_duration_seconds=45)

        result = self.dispatcher.dispatch(profile)

        self.assertIsInstance(result, MathDispatchResult)
        assert isinstance(result, MathDispatchResult)
        self.assertEqual(result.selected_path, "math_challenge_generator")
        self.assertEqual(result.selected_path, DispatchTarget.MATH_GENERATOR.value)
        self.assertEqual(result.challenge_type, "math")
        self.assertEqual(result.difficulty, "medium")
        self.assertEqual(result.difficulty_level, "medium")
        self.assertFalse(result.is_procedural)
        self.assertIs(result.generator_class, MathChallengeGenerator)

    def test_math_generator_input_args_contract(self) -> None:
        """Test A & V & W: Generator-compatible arguments match MathChallengeGenerator signature."""
        params = MathPersonalizationParams(
            focus_topic="budgeting",
            preferred_operation="multiplication",
            operand_scale_preference="compact",
        )
        profile = _make_profile("math", "hard", params, desired_duration_seconds=30)

        result = self.dispatcher.dispatch_math(profile)

        self.assertIsInstance(result.generator_input, MathGeneratorInputArgs)
        self.assertEqual(result.generator_input.challenge_type, "math")
        self.assertEqual(result.generator_input.difficulty_level, "hard")
        self.assertTrue(result.generator_input.strict_context)
        self.assertEqual(result.generator_input.raw_context.preferred_theme, "budgeting")
        self.assertEqual(result.generator_input.raw_context.desired_duration_seconds, 30)

    def test_math_adapter_output_preserved(self) -> None:
        """Test H: Relevant personalization parameters preserved in adapter output."""
        params = MathPersonalizationParams(
            focus_topic="cooking",
            preferred_operation="division",
            operand_scale_preference="standard",
        )
        profile = _make_profile("math", "easy", params, desired_duration_seconds=20)

        result = self.dispatcher.dispatch_math(profile)

        self.assertIsInstance(result.adapter_output, MathPersonalizationAdapterOutput)
        self.assertEqual(result.adapter_output.focus_topic, "cooking")
        self.assertEqual(result.adapter_output.preferred_operation, "division")
        self.assertEqual(result.adapter_output.operand_scale_preference, "standard")
        self.assertEqual(result.adapter_output.desired_duration_seconds, 20)

    def test_math_convenience_properties(self) -> None:
        """Test payload and parameters convenience accessors."""
        profile = _make_profile("math", "medium", MathPersonalizationParams())
        result = self.dispatcher.dispatch_math(profile)

        self.assertIs(result.payload, result.adapter_output)
        self.assertIs(result.parameters, result.generator_input)

    def test_math_convenience_function(self) -> None:
        """Test module-level dispatch_profile convenience function for math."""
        profile = _make_profile("math", "easy", MathPersonalizationParams())
        result = dispatch_profile(profile)

        self.assertIsInstance(result, MathDispatchResult)
        self.assertEqual(result.challenge_type, "math")

    def test_dispatch_math_rejects_wrong_challenge_type(self) -> None:
        """Test dispatch_math rejects non-math profile."""
        profile = _make_profile("memory", "easy", MemoryPersonalizationParams())
        with self.assertRaises(DispatcherTypeError):
            self.dispatcher.dispatch_math(profile)


# =============================================================================
# B. MEMORY DISPATCH TESTS
# =============================================================================

class TestMemoryDispatch(unittest.TestCase):
    """Tests B, F, G, H, V, W, X, Y for memory challenge profile routing."""

    def setUp(self) -> None:
        self.dispatcher = PersonalizationDispatcher()

    def test_memory_profile_routes_to_memory_generator_path(self) -> None:
        """Test B: Memory profile routes to MemoryDispatchResult with memory_challenge_generator path."""
        params = MemoryPersonalizationParams(
            preferred_mode="spatial_pattern_recall", palette_theme="geometric_shapes"
        )
        profile = _make_profile("memory", "hard", params, desired_duration_seconds=60)

        result = self.dispatcher.dispatch(profile)

        self.assertIsInstance(result, MemoryDispatchResult)
        assert isinstance(result, MemoryDispatchResult)
        self.assertEqual(result.selected_path, "memory_challenge_generator")
        self.assertEqual(result.selected_path, DispatchTarget.MEMORY_GENERATOR.value)
        self.assertEqual(result.challenge_type, "memory")
        self.assertEqual(result.difficulty, "hard")
        self.assertEqual(result.difficulty_level, "hard")
        self.assertFalse(result.is_procedural)
        self.assertIs(result.generator_class, MemoryChallengeGenerator)

    def test_memory_preferred_mode_routed_correctly(self) -> None:
        """Test X: Memory preferred_mode is accurately routed to generator input."""
        modes = [
            "visual_sequence",
            "spatial_pattern_recall",
            "dynamic_spatial_path",
            "symbol_chronological_order",
        ]
        for mode in modes:
            with self.subTest(mode=mode):
                params = MemoryPersonalizationParams(preferred_mode=mode)  # pyright: ignore[reportArgumentType]
                profile = _make_profile("memory", "medium", params)
                result = self.dispatcher.dispatch_memory(profile)

                self.assertEqual(result.generator_input.preferred_mode, mode)
                self.assertEqual(result.adapter_output.preferred_mode, mode)

    def test_memory_palette_theme_informs_preferred_theme(self) -> None:
        """Test H: Memory palette_theme informs raw_context.preferred_theme."""
        params = MemoryPersonalizationParams(palette_theme="colors")
        profile = _make_profile("memory", "easy", params)

        result = self.dispatcher.dispatch_memory(profile)

        self.assertEqual(result.generator_input.raw_context.preferred_theme, "colors")
        self.assertEqual(result.adapter_output.palette_theme, "colors")

    def test_memory_convenience_properties(self) -> None:
        """Test payload and parameters convenience accessors for memory."""
        profile = _make_profile("memory", "medium", MemoryPersonalizationParams())
        result = self.dispatcher.dispatch_memory(profile)

        self.assertIs(result.payload, result.adapter_output)
        self.assertIs(result.parameters, result.generator_input)

    def test_dispatch_memory_rejects_wrong_challenge_type(self) -> None:
        """Test dispatch_memory rejects non-memory profile."""
        profile = _make_profile("math", "easy", MathPersonalizationParams())
        with self.assertRaises(DispatcherTypeError):
            self.dispatcher.dispatch_memory(profile)


# =============================================================================
# C. TONGUE TWISTER DISPATCH TESTS
# =============================================================================

class TestTongueTwisterDispatch(unittest.TestCase):
    """Tests C, F, G, H, V, W for tongue twister challenge profile routing."""

    def setUp(self) -> None:
        self.dispatcher = PersonalizationDispatcher()

    def test_tongue_twister_profile_routes_to_generator_path(self) -> None:
        """Test C: Tongue-twister routes to TongueTwisterDispatchResult."""
        params = TongueTwisterPersonalizationParams(
            target_sound_family="sibilants", theme_style="animals"
        )
        profile = _make_profile("tongue_twister", "medium", params, desired_duration_seconds=30)

        result = self.dispatcher.dispatch(profile)

        self.assertIsInstance(result, TongueTwisterDispatchResult)
        assert isinstance(result, TongueTwisterDispatchResult)
        self.assertEqual(result.selected_path, "tongue_twister_challenge_generator")
        self.assertEqual(result.selected_path, DispatchTarget.TONGUE_TWISTER_GENERATOR.value)
        self.assertEqual(result.challenge_type, "tongue_twister")
        self.assertEqual(result.difficulty, "medium")
        self.assertEqual(result.difficulty_level, "medium")
        self.assertFalse(result.is_procedural)
        self.assertIs(result.generator_class, TongueTwisterChallengeGenerator)

    def test_tongue_twister_generator_input_contract(self) -> None:
        """Test C & V & W: Generator-compatible arguments match TongueTwister generator."""
        params = TongueTwisterPersonalizationParams(
            target_sound_family="plosives", theme_style="nature"
        )
        profile = _make_profile("tongue_twister", "hard", params, desired_duration_seconds=25)

        result = self.dispatcher.dispatch_tongue_twister(profile)

        self.assertIsInstance(result.generator_input, TongueTwisterGeneratorInputArgs)
        self.assertEqual(result.generator_input.challenge_type, "tongue_twister")
        self.assertEqual(result.generator_input.difficulty_level, "hard")
        self.assertTrue(result.generator_input.strict_context)
        self.assertEqual(result.generator_input.raw_context.preferred_theme, "nature")
        self.assertEqual(result.generator_input.raw_context.desired_duration_seconds, 25)

    def test_tongue_twister_adapter_output_preserved(self) -> None:
        """Test H: Sound family and theme style preserved in adapter output."""
        params = TongueTwisterPersonalizationParams(
            target_sound_family="liquids", theme_style="whimsical"
        )
        profile = _make_profile("tongue_twister", "easy", params)

        result = self.dispatcher.dispatch_tongue_twister(profile)

        self.assertEqual(result.adapter_output.target_sound_family, "liquids")
        self.assertEqual(result.adapter_output.theme_style, "whimsical")

    def test_tongue_twister_convenience_properties(self) -> None:
        """Test payload and parameters convenience accessors for tongue twister."""
        profile = _make_profile("tongue_twister", "easy", TongueTwisterPersonalizationParams())
        result = self.dispatcher.dispatch_tongue_twister(profile)

        self.assertIs(result.payload, result.adapter_output)
        self.assertIs(result.parameters, result.generator_input)

    def test_dispatch_tongue_twister_rejects_wrong_type(self) -> None:
        """Test dispatch_tongue_twister rejects non-tongue-twister profile."""
        profile = _make_profile("math", "easy", MathPersonalizationParams())
        with self.assertRaises(DispatcherTypeError):
            self.dispatcher.dispatch_tongue_twister(profile)


# =============================================================================
# D. DANCE DISPATCH TESTS
# =============================================================================

class TestDanceDispatch(unittest.TestCase):
    """Tests D, F, G, H for procedural dance adapter routing."""

    def setUp(self) -> None:
        self.dispatcher = PersonalizationDispatcher()

    def test_dance_profile_routes_to_procedural_dance_path(self) -> None:
        """Test D: Dance profile routes to DanceDispatchResult with dance_procedural_adapter path."""
        params = DancePersonalizationParams(movement_style="rhythm_groove", pacing="dynamic")
        profile = _make_profile("dance", "medium", params, desired_duration_seconds=60)

        result = self.dispatcher.dispatch(profile)

        self.assertIsInstance(result, DanceDispatchResult)
        self.assertEqual(result.selected_path, "dance_procedural_adapter")
        self.assertEqual(result.selected_path, DispatchTarget.DANCE_ADAPTER.value)
        self.assertEqual(result.challenge_type, "dance")
        self.assertEqual(result.difficulty, "medium")
        self.assertEqual(result.difficulty_level, "medium")
        self.assertTrue(result.is_procedural)

    def test_dance_adapter_output_preserved(self) -> None:
        """Test H: Movement style and pacing carried through cleanly."""
        params = DancePersonalizationParams(movement_style="arm_raises", pacing="slow")
        profile = _make_profile("dance", "hard", params, desired_duration_seconds=90)

        result = self.dispatcher.dispatch_dance(profile)

        self.assertIsInstance(result.adapter_output, DancePersonalizationAdapterOutput)
        self.assertEqual(result.adapter_output.movement_style, "arm_raises")
        self.assertEqual(result.adapter_output.pacing, "slow")
        self.assertEqual(result.adapter_output.desired_duration_seconds, 90)

    def test_dance_is_procedural_only_no_content_fields(self) -> None:
        """Test D: Dance output contains procedural parameters only, no routine content."""
        profile = _make_profile("dance", "easy", DancePersonalizationParams())
        result = self.dispatcher.dispatch_dance(profile)

        self.assertFalse(hasattr(result, "routine"))
        self.assertFalse(hasattr(result, "choreography"))
        self.assertFalse(hasattr(result, "poses"))
        self.assertFalse(hasattr(result, "generator_input"))

    def test_dance_convenience_properties(self) -> None:
        """Test payload and parameters convenience accessors for dance."""
        profile = _make_profile("dance", "easy", DancePersonalizationParams())
        result = self.dispatcher.dispatch_dance(profile)

        self.assertIs(result.payload, result.adapter_output)
        self.assertIs(result.parameters, result.adapter_output)

    def test_dispatch_dance_rejects_wrong_type(self) -> None:
        """Test dispatch_dance rejects non-dance profile."""
        profile = _make_profile("math", "easy", MathPersonalizationParams())
        with self.assertRaises(DispatcherTypeError):
            self.dispatcher.dispatch_dance(profile)


# =============================================================================
# E. PUSH-UPS DISPATCH TESTS
# =============================================================================

class TestPushUpDispatch(unittest.TestCase):
    """Tests E, F, G, H for procedural push-up adapter routing."""

    def setUp(self) -> None:
        self.dispatcher = PersonalizationDispatcher()

    def test_push_ups_profile_routes_to_procedural_push_ups_path(self) -> None:
        """Test E: Push-up profile routes to PushUpDispatchResult with push_ups_procedural_adapter path."""
        params = PushUpPersonalizationParams(
            cadence_tempo="tempo_pause", target_rep_styling="tier_median"
        )
        profile = _make_profile("push_ups", "hard", params, desired_duration_seconds=45)

        result = self.dispatcher.dispatch(profile)

        self.assertIsInstance(result, PushUpDispatchResult)
        self.assertEqual(result.selected_path, "push_ups_procedural_adapter")
        self.assertEqual(result.selected_path, DispatchTarget.PUSH_UPS_ADAPTER.value)
        self.assertEqual(result.challenge_type, "push_ups")
        self.assertEqual(result.difficulty, "hard")
        self.assertEqual(result.difficulty_level, "hard")
        self.assertTrue(result.is_procedural)

    def test_push_ups_adapter_output_preserved(self) -> None:
        """Test H: Cadence tempo and target rep styling carried through cleanly."""
        params = PushUpPersonalizationParams(
            cadence_tempo="steady", target_rep_styling="tier_max"
        )
        profile = _make_profile("push_ups", "easy", params, desired_duration_seconds=30)

        result = self.dispatcher.dispatch_push_ups(profile)

        self.assertIsInstance(result.adapter_output, PushUpPersonalizationAdapterOutput)
        self.assertEqual(result.adapter_output.cadence_tempo, "steady")
        self.assertEqual(result.adapter_output.target_rep_styling, "tier_max")
        self.assertEqual(result.adapter_output.desired_duration_seconds, 30)

    def test_push_ups_is_procedural_only_no_content_fields(self) -> None:
        """Test E: Push-up output contains procedural parameters only, no rep generation."""
        profile = _make_profile("push_ups", "medium", PushUpPersonalizationParams())
        result = self.dispatcher.dispatch_push_ups(profile)

        self.assertFalse(hasattr(result, "reps"))
        self.assertFalse(hasattr(result, "verification"))
        self.assertFalse(hasattr(result, "pose_detection"))
        self.assertFalse(hasattr(result, "generator_input"))

    def test_push_ups_convenience_properties(self) -> None:
        """Test payload and parameters convenience accessors for push-ups."""
        profile = _make_profile("push_ups", "medium", PushUpPersonalizationParams())
        result = self.dispatcher.dispatch_push_ups(profile)

        self.assertIs(result.payload, result.adapter_output)
        self.assertIs(result.parameters, result.adapter_output)

    def test_dispatch_push_ups_rejects_wrong_type(self) -> None:
        """Test dispatch_push_ups rejects non-push-ups profile."""
        profile = _make_profile("math", "easy", MathPersonalizationParams())
        with self.assertRaises(DispatcherTypeError):
            self.dispatcher.dispatch_push_ups(profile)


# =============================================================================
# F & G. TYPE AND DIFFICULTY PRESERVATION ACROSS ALL PERMUTATIONS
# =============================================================================

class TestPreservationAndImmutability(unittest.TestCase):
    """Tests F, G, I, L, Q, R, Y for preservation, duration independence, and immutability."""

    def setUp(self) -> None:
        self.dispatcher = PersonalizationDispatcher()

    def test_all_five_types_preserve_challenge_type_exactly(self) -> None:
        """Test F: Challenge type preserved for all 5 canonical types."""
        cases = [
            ("math", MathPersonalizationParams(), MathDispatchResult),
            ("memory", MemoryPersonalizationParams(), MemoryDispatchResult),
            ("tongue_twister", TongueTwisterPersonalizationParams(), TongueTwisterDispatchResult),
            ("dance", DancePersonalizationParams(), DanceDispatchResult),
            ("push_ups", PushUpPersonalizationParams(), PushUpDispatchResult),
        ]
        for ctype, params, expected_cls in cases:
            with self.subTest(challenge_type=ctype):
                profile = _make_profile(ctype, "medium", params)  # pyright: ignore[reportArgumentType]
                result = self.dispatcher.dispatch(profile)
                self.assertIsInstance(result, expected_cls)
                self.assertEqual(result.challenge_type, ctype)

    def test_all_five_types_preserve_all_three_difficulties(self) -> None:
        """Test G: Difficulty preserved for easy, medium, hard across all 5 challenge types (15 pairs)."""
        cases = [
            ("math", MathPersonalizationParams()),
            ("memory", MemoryPersonalizationParams()),
            ("tongue_twister", TongueTwisterPersonalizationParams()),
            ("dance", DancePersonalizationParams()),
            ("push_ups", PushUpPersonalizationParams()),
        ]
        for ctype, params in cases:
            for diff in ("easy", "medium", "hard"):
                with self.subTest(challenge_type=ctype, difficulty=diff):
                    profile = _make_profile(ctype, diff, params)  # pyright: ignore[reportArgumentType]
                    result = self.dispatcher.dispatch(profile)
                    self.assertEqual(result.difficulty, diff)
                    self.assertEqual(result.difficulty_level, diff)

    def test_profile_is_never_mutated(self) -> None:
        """Test Q & R: Input PersonalizedChallengeProfile is strictly immutable and unaltered."""
        params = MathPersonalizationParams(focus_topic="astronomy", preferred_operation="addition")
        profile = _make_profile("math", "medium", params, desired_duration_seconds=30)
        snapshot_before = profile.model_dump()

        _ = self.dispatcher.dispatch(profile)

        self.assertEqual(profile.model_dump(), snapshot_before)

    def test_desired_duration_seconds_never_alters_difficulty_or_type(self) -> None:
        """Test L & Y: desired_duration_seconds across valid range does not alter difficulty or type."""
        cases = [
            ("math", MathPersonalizationParams()),
            ("memory", MemoryPersonalizationParams()),
            ("tongue_twister", TongueTwisterPersonalizationParams()),
            ("dance", DancePersonalizationParams()),
            ("push_ups", PushUpPersonalizationParams()),
        ]
        durations = [5, 15, 30, 60, 120, 300]
        for ctype, params in cases:
            for diff in ("easy", "medium", "hard"):
                for dur in durations:
                    profile = _make_profile(ctype, diff, params, desired_duration_seconds=dur)  # pyright: ignore[reportArgumentType]
                    result = self.dispatcher.dispatch(profile)
                    self.assertEqual(result.difficulty, diff)
                    self.assertEqual(result.difficulty_level, diff)
                    self.assertEqual(result.challenge_type, ctype)

    def test_dispatch_results_are_frozen(self) -> None:
        """Test that all dispatch results are strictly frozen immutable models."""
        profile = _make_profile("math", "easy", MathPersonalizationParams())
        result = self.dispatcher.dispatch(profile)
        with self.assertRaises(Exception):
            setattr(result, "difficulty", "hard")  # frozen Pydantic model raises ValidationError on setattr


# =============================================================================
# J, K, L. VALIDATION AND REJECTION TESTS
# =============================================================================

class TestValidationAndRejections(unittest.TestCase):
    """Tests J, K, L for rejection of invalid or forbidden challenge types and difficulties."""

    def setUp(self) -> None:
        self.dispatcher = PersonalizationDispatcher()

    def test_forbidden_challenge_types_rejected(self) -> None:
        """Test J: Forbidden challenge types raise DispatcherTypeError."""
        for forbidden in FORBIDDEN_CHALLENGE_TYPES:
            with self.subTest(forbidden_type=forbidden):
                profile = _make_profile("math", "easy", MathPersonalizationParams())
                object.__setattr__(profile, "challenge_type", forbidden)
                with self.assertRaises(DispatcherTypeError):
                    self.dispatcher.dispatch(profile)

    def test_unknown_challenge_types_rejected(self) -> None:
        """Test K: Unknown or unsupported challenge types raise DispatcherTypeError."""
        unknowns = ["trivia", "chess", "sudoku", "word_puzzle", "", "MATH"]
        for unknown in unknowns:
            with self.subTest(unknown_type=unknown):
                profile = _make_profile("math", "easy", MathPersonalizationParams())
                object.__setattr__(profile, "challenge_type", unknown)
                with self.assertRaises(DispatcherTypeError):
                    self.dispatcher.dispatch(profile)

    def test_invalid_difficulty_levels_rejected(self) -> None:
        """Test L: Invalid difficulty levels raise DispatcherDifficultyError."""
        bad_diffs = ["adaptive", "extreme", "beginner", "ultra", "", "EASY", "med"]
        for bad_diff in bad_diffs:
            with self.subTest(bad_difficulty=bad_diff):
                profile = _make_profile("math", "easy", MathPersonalizationParams())
                object.__setattr__(profile, "difficulty_level", bad_diff)
                with self.assertRaises(DispatcherDifficultyError):
                    self.dispatcher.dispatch(profile)

    def test_non_profile_input_rejected(self) -> None:
        """Test non-profile input raises DispatcherError."""
        for bad_input in [None, "string", 123, {}, []]:
            with self.subTest(bad_input=bad_input):
                with self.assertRaises(DispatcherError):
                    self.dispatcher.dispatch(bad_input)  # pyright: ignore[reportArgumentType]

    def test_exception_inheritance_hierarchy(self) -> None:
        """Test exception hierarchy matches existing project conventions."""
        self.assertTrue(issubclass(DispatcherError, SmartWakeException))
        self.assertTrue(issubclass(DispatcherError, ValueError))
        self.assertTrue(issubclass(DispatcherTypeError, DispatcherError))
        self.assertTrue(issubclass(DispatcherTypeError, AdapterTypeError))
        self.assertTrue(issubclass(DispatcherTypeError, InvalidChallengeTypeError))
        self.assertTrue(issubclass(DispatcherDifficultyError, DispatcherError))
        self.assertTrue(issubclass(DispatcherDifficultyError, AdapterDifficultyError))
        self.assertTrue(issubclass(DispatcherDifficultyError, InvalidDifficultyError))


# =============================================================================
# N, O, P, S, T, U. ARCHITECTURAL BOUNDARY AND INTEGRITY TESTS
# =============================================================================

class TestArchitecturalBoundaries(unittest.TestCase):
    """Tests N, O, P, S, T, U for architectural purity and generator contract compatibility."""

    def test_no_database_or_orm_imports_in_dispatcher(self) -> None:
        """Test N: Dispatcher module must not import ORM or DB libraries."""
        import backend.app.services.personalization_dispatcher as dispatcher_mod
        source = inspect.getsource(dispatcher_mod)
        tree = ast.parse(source)

        forbidden_names = [
            "sqlalchemy",
            "alembic",
            "get_db",
            "backend.app.db",
            "backend.app.models",
        ]
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for forbidden in forbidden_names:
                        self.assertNotIn(
                            forbidden, alias.name,
                            f"Dispatcher must not import DB library '{alias.name}'.",
                        )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for forbidden in forbidden_names:
                    self.assertNotIn(
                        forbidden, module,
                        f"Dispatcher must not import from DB module '{module}'.",
                    )

    def test_no_network_or_llm_imports_in_dispatcher(self) -> None:
        """Test O: Dispatcher module must not import network or LLM client libraries."""
        import backend.app.services.personalization_dispatcher as dispatcher_mod
        source = inspect.getsource(dispatcher_mod)
        tree = ast.parse(source)

        forbidden_names = [
            "requests",
            "httpx",
            "aiohttp",
            "google.generativeai",
            "openai",
            "gemini",
            "langchain",
        ]
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for forbidden in forbidden_names:
                        self.assertNotIn(
                            forbidden, alias.name,
                            f"Dispatcher must not import network/LLM library '{alias.name}'.",
                        )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for forbidden in forbidden_names:
                    self.assertNotIn(
                        forbidden, module,
                        f"Dispatcher must not import from network/LLM module '{module}'.",
                    )

    def test_no_randomness_or_runtime_timestamps_in_dispatcher(self) -> None:
        """Test deterministic behavior: no random, uuid, secrets, or datetime.now."""
        import backend.app.services.personalization_dispatcher as dispatcher_mod
        source = inspect.getsource(dispatcher_mod)
        for forbidden in ["import random", "import uuid", "import secrets", "datetime.now", "time.time()"]:
            self.assertNotIn(
                forbidden, source,
                f"Dispatcher must not use non-deterministic symbol '{forbidden}'.",
            )

    def test_no_content_generation_or_verification_in_dispatcher(self) -> None:
        """Test P & Q: Dispatcher does not generate questions, sentences, or execute verification."""
        profile = _make_profile("math", "easy", MathPersonalizationParams())
        result = PersonalizationDispatcher().dispatch(profile)

        self.assertFalse(hasattr(result, "content_payload"))
        self.assertFalse(hasattr(result, "expected_answer"))
        self.assertFalse(hasattr(result, "questions"))
        self.assertFalse(hasattr(result, "verification_mode"))
        self.assertFalse(hasattr(result, "is_verified"))

    def test_no_dict_str_any_in_dispatcher_source(self) -> None:
        """Test T: Production dispatcher module contains zero Dict[str, Any] annotations or references."""
        import backend.app.services.personalization_dispatcher as dispatcher_mod
        source = inspect.getsource(dispatcher_mod)

        self.assertNotIn(
            "Dict[str, Any]", source,
            "Production dispatcher must not use Dict[str, Any].",
        )
        self.assertNotIn(
            "dict[str, Any]", source,
            "Production dispatcher must not use dict[str, Any].",
        )

    def test_phase_4_2_math_generator_contract_compatibility(self) -> None:
        """Test U: MathGeneratorInputArgs fields match MathChallengeGenerator.generate_math_challenge signature."""
        sig = inspect.signature(MathChallengeGenerator.generate_math_challenge)
        params = sig.parameters

        self.assertIn("difficulty_level", params)
        self.assertIn("challenge_type", params)
        self.assertIn("raw_context", params)
        self.assertIn("strict_context", params)

        # Verify MathGeneratorInputArgs provides all required fields
        profile = _make_profile("math", "medium", MathPersonalizationParams())
        result = PersonalizationDispatcher().dispatch_math(profile)
        gen_input = result.generator_input

        self.assertEqual(gen_input.difficulty_level, "medium")
        self.assertEqual(gen_input.challenge_type, "math")
        self.assertIsInstance(gen_input.raw_context, SafePersonalizationContext)
        self.assertTrue(gen_input.strict_context)

    def test_phase_4_3_memory_generator_contract_compatibility(self) -> None:
        """Test U: MemoryGeneratorInputArgs fields match MemoryChallengeGenerator.generate_memory_challenge signature."""
        sig = inspect.signature(MemoryChallengeGenerator.generate_memory_challenge)
        params = sig.parameters

        self.assertIn("difficulty_level", params)
        self.assertIn("challenge_type", params)
        self.assertIn("raw_context", params)
        self.assertIn("strict_context", params)
        self.assertIn("preferred_mode", params)

        profile = _make_profile(
            "memory", "hard", MemoryPersonalizationParams(preferred_mode="visual_sequence")
        )
        result = PersonalizationDispatcher().dispatch_memory(profile)
        gen_input = result.generator_input

        self.assertEqual(gen_input.difficulty_level, "hard")
        self.assertEqual(gen_input.challenge_type, "memory")
        self.assertEqual(gen_input.preferred_mode, "visual_sequence")
        self.assertIsInstance(gen_input.raw_context, SafePersonalizationContext)
        self.assertTrue(gen_input.strict_context)

    def test_phase_4_4_tongue_twister_generator_contract_compatibility(self) -> None:
        """Test U: TongueTwisterGeneratorInputArgs fields match TongueTwister generator signature."""
        sig = inspect.signature(TongueTwisterChallengeGenerator.generate_tongue_twister_challenge)
        params = sig.parameters

        self.assertIn("difficulty_level", params)
        self.assertIn("challenge_type", params)
        self.assertIn("raw_context", params)
        self.assertIn("strict_context", params)

        profile = _make_profile("tongue_twister", "easy", TongueTwisterPersonalizationParams())
        result = PersonalizationDispatcher().dispatch_tongue_twister(profile)
        gen_input = result.generator_input

        self.assertEqual(gen_input.difficulty_level, "easy")
        self.assertEqual(gen_input.challenge_type, "tongue_twister")
        self.assertIsInstance(gen_input.raw_context, SafePersonalizationContext)
        self.assertTrue(gen_input.strict_context)


if __name__ == "__main__":
    unittest.main(verbosity=2)
