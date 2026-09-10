"""Tests for Phase 4.5 Step 4: Procedural Personalization Adapters.

Covers all 24 required test scenarios:
 1.  Math profile -> MathPersonalizationAdapterOutput
 2.  Memory profile -> MemoryPersonalizationAdapterOutput
 3.  Tongue-twister profile -> TongueTwisterPersonalizationAdapterOutput
 4.  Dance profile -> DancePersonalizationAdapterOutput (procedural only)
 5.  Push-up profile -> PushUpPersonalizationAdapterOutput (procedural only)
 6.  challenge_type remains unchanged
 7.  difficulty_level remains unchanged
 8.  Wrong parameter model for challenge_type raises AdapterParameterMismatchError
 9.  Forbidden challenge type raises AdapterTypeError
10.  Invalid difficulty level raises AdapterDifficultyError
11.  Unsupported personalization fields safely ignored (adapter omits them)
12.  No actual challenge content is generated
13.  No LLM/provider/network calls (pure deterministic function)
14.  No database/ORM access
15.  No randomization (identical input -> identical output)
16.  desired_duration_seconds remains generation styling only (no difficulty mutation)
17.  Phase 4.2 math generator contract remains compatible
18.  Phase 4.3 memory generator contract remains compatible
19.  Phase 4.4 tongue-twister generator contract remains compatible
20.  Dance and push-up outputs remain procedural-only (no content fields)
21.  Strict typed outputs (isinstance checks on all five output models)
22.  No Dict[str, Any] in outputs
23.  Deterministic output for identical profiles
24.  All five canonical challenge types are covered

Note on Pyright narrowing strategy:
  - Tests that access type-specific attributes use the concrete per-type adapters
    (_adapt_math, _adapt_memory, etc.) which return concrete types, allowing
    Pyright to narrow the type at compile time.
  - Tests that only check shared fields (challenge_type, difficulty_level,
    desired_duration_seconds) or use hasattr/assertIsInstance use adapt_profile
    (union return), which is safe because those fields exist on all union members.
"""
import inspect
import unittest
from typing import Optional

from backend.app.schemas.personalization_content_schemas import (
    BehavioralPersonalizationSignals,
    DancePersonalizationParams,
    MathPersonalizationParams,
    MemoryPersonalizationParams,
    PersonalizedChallengeProfile,
    PushUpPersonalizationParams,
    TongueTwisterPersonalizationParams,
)
from backend.app.schemas.challenge_content_schemas import SafePersonalizationContext
from backend.app.services.genai.personalization_adapters import (
    AdapterDifficultyError,
    AdapterParameterMismatchError,
    AdapterTypeError,
    DancePersonalizationAdapterOutput,
    MathPersonalizationAdapterOutput,
    MemoryPersonalizationAdapterOutput,
    PushUpPersonalizationAdapterOutput,
    TongueTwisterPersonalizationAdapterOutput,
    adapt_profile,
    _adapt_math,
    _adapt_memory,
    _adapt_tongue_twister,
    _adapt_dance,
    _adapt_push_ups,
    _validate_type_and_difficulty,
)


from typing import Any, cast
from backend.app.schemas.personalization_content_schemas import (
    CanonicalChallengeType,
    CanonicalDifficultyLevel,
)


def _make_profile(
    challenge_type: str,
    difficulty_level: str = "medium",
    typed_parameters: Any = None,
    desired_duration_seconds: Optional[int] = None,
) -> PersonalizedChallengeProfile:
    """Build a minimal PersonalizedChallengeProfile for testing."""
    safe_ctx = SafePersonalizationContext(
        desired_duration_seconds=desired_duration_seconds,
        current_session_snooze_count=0,
        current_attempt_number=1,
        preferred_theme=None,
    )
    return PersonalizedChallengeProfile(
        challenge_type=cast(CanonicalChallengeType, challenge_type),
        difficulty_level=cast(CanonicalDifficultyLevel, difficulty_level),
        safe_context=safe_ctx,
        behavioral_signals=BehavioralPersonalizationSignals(),
        recent_structural_signatures=[],
        typed_parameters=typed_parameters,
    )


class TestMathAdapter(unittest.TestCase):
    """Tests 1, 6, 7, 12, 13, 14, 15, 17, 21, 22, 23, 24 (math slice)."""

    def test_returns_math_adapter_output(self):
        """Test 1: math profile -> MathPersonalizationAdapterOutput."""
        params = MathPersonalizationParams(
            focus_topic="astronomy",
            preferred_operation="addition",
            operand_scale_preference="compact",
        )
        profile = _make_profile("math", "easy", params)
        result = _adapt_math(profile)
        self.assertIsInstance(result, MathPersonalizationAdapterOutput)

    def test_challenge_type_preserved(self):
        """Test 6: challenge_type remains math."""
        profile = _make_profile("math", "medium", MathPersonalizationParams())
        result = _adapt_math(profile)
        self.assertEqual(result.challenge_type, "math")

    def test_difficulty_preserved_easy(self):
        """Test 7: difficulty_level easy preserved exactly."""
        profile = _make_profile("math", "easy", MathPersonalizationParams())
        result = _adapt_math(profile)
        self.assertEqual(result.difficulty_level, "easy")

    def test_difficulty_preserved_hard(self):
        """Test 7: difficulty_level hard preserved exactly."""
        profile = _make_profile("math", "hard", MathPersonalizationParams())
        result = _adapt_math(profile)
        self.assertEqual(result.difficulty_level, "hard")

    def test_focus_topic_mapped(self):
        """Test 1 detail: focus_topic carried through."""
        params = MathPersonalizationParams(focus_topic="budgeting")
        profile = _make_profile("math", "medium", params)
        result = _adapt_math(profile)
        self.assertEqual(result.focus_topic, "budgeting")

    def test_preferred_operation_mapped(self):
        """Test 1 detail: preferred_operation carried through."""
        params = MathPersonalizationParams(preferred_operation="multiplication")
        profile = _make_profile("math", "medium", params)
        result = _adapt_math(profile)
        self.assertEqual(result.preferred_operation, "multiplication")

    def test_operand_scale_preference_mapped(self):
        """Test 1 detail: operand_scale_preference carried through."""
        params = MathPersonalizationParams(operand_scale_preference="standard")
        profile = _make_profile("math", "medium", params)
        result = _adapt_math(profile)
        self.assertEqual(result.operand_scale_preference, "standard")

    def test_no_params_gives_none_fields(self):
        """Test 11: No typed_parameters -> all mapped fields are None."""
        profile = _make_profile("math", "medium", None)
        result = _adapt_math(profile)
        self.assertIsInstance(result, MathPersonalizationAdapterOutput)
        self.assertIsNone(result.focus_topic)
        self.assertIsNone(result.preferred_operation)
        self.assertIsNone(result.operand_scale_preference)

    def test_desired_duration_seconds_carried(self):
        """Test 16: desired_duration_seconds propagated as hint only."""
        profile = _make_profile("math", "medium", MathPersonalizationParams(),
                                desired_duration_seconds=60)
        result = _adapt_math(profile)
        self.assertEqual(result.desired_duration_seconds, 60)
        self.assertEqual(result.difficulty_level, "medium")

    def test_desired_duration_none_when_not_set(self):
        """Test 16: desired_duration_seconds is None when not provided."""
        profile = _make_profile("math", "medium", MathPersonalizationParams())
        result = _adapt_math(profile)
        self.assertIsNone(result.desired_duration_seconds)

    def test_no_content_generation(self):
        """Test 12: Output must NOT contain question/expression/answer fields."""
        profile = _make_profile("math", "easy", MathPersonalizationParams())
        result = _adapt_math(profile)
        self.assertFalse(hasattr(result, "question"))
        self.assertFalse(hasattr(result, "expression"))
        self.assertFalse(hasattr(result, "answer"))
        self.assertFalse(hasattr(result, "questions"))
        self.assertFalse(hasattr(result, "content_payload"))

    def test_output_is_typed_pydantic_not_dict(self):
        """Test 21 and 22: Output is Pydantic model not a raw dict."""
        profile = _make_profile("math", "medium", MathPersonalizationParams())
        result = _adapt_math(profile)
        self.assertNotIsInstance(result, dict)
        self.assertIsInstance(result, MathPersonalizationAdapterOutput)

    def test_deterministic_for_identical_profiles(self):
        """Test 23: Identical inputs produce identical outputs."""
        params = MathPersonalizationParams(
            focus_topic="morning_routine",
            preferred_operation="addition",
            operand_scale_preference="compact",
        )
        p1 = _make_profile("math", "hard", params, desired_duration_seconds=30)
        p2 = _make_profile("math", "hard", params, desired_duration_seconds=30)
        self.assertEqual(_adapt_math(p1), _adapt_math(p2))

    def test_phase42_contract_no_memory_fields(self):
        """Test 17: Math output must not contain memory-specific fields."""
        profile = _make_profile("math", "medium", MathPersonalizationParams())
        result = _adapt_math(profile)
        self.assertFalse(hasattr(result, "preferred_mode"))
        self.assertFalse(hasattr(result, "palette_theme"))
        self.assertFalse(hasattr(result, "recall_mode"))

    def test_phase42_contract_no_tongue_twister_fields(self):
        """Test 17: Math output must not contain tongue-twister-specific fields."""
        profile = _make_profile("math", "medium", MathPersonalizationParams())
        result = _adapt_math(profile)
        self.assertFalse(hasattr(result, "target_sound_family"))
        self.assertFalse(hasattr(result, "theme_style"))
        self.assertFalse(hasattr(result, "passage"))

    def test_adapt_profile_dispatches_to_math(self):
        """Test 24: adapt_profile dispatches math correctly."""
        profile = _make_profile("math", "medium", MathPersonalizationParams())
        result = adapt_profile(profile)
        self.assertIsInstance(result, MathPersonalizationAdapterOutput)
        self.assertEqual(result.challenge_type, "math")


class TestMemoryAdapter(unittest.TestCase):
    """Tests 2, 6, 7, 12, 18, 21, 22, 23, 24 (memory slice)."""

    def test_returns_memory_adapter_output(self):
        """Test 2: memory profile -> MemoryPersonalizationAdapterOutput."""
        params = MemoryPersonalizationParams(
            preferred_mode="visual_sequence",
            palette_theme="colors",
        )
        profile = _make_profile("memory", "medium", params)
        result = _adapt_memory(profile)
        self.assertIsInstance(result, MemoryPersonalizationAdapterOutput)

    def test_challenge_type_preserved(self):
        """Test 6: challenge_type remains memory."""
        profile = _make_profile("memory", "easy", MemoryPersonalizationParams())
        result = _adapt_memory(profile)
        self.assertEqual(result.challenge_type, "memory")

    def test_difficulty_preserved(self):
        """Test 7: difficulty_level preserved exactly."""
        profile = _make_profile("memory", "hard", MemoryPersonalizationParams())
        result = _adapt_memory(profile)
        self.assertEqual(result.difficulty_level, "hard")

    def test_preferred_mode_mapped(self):
        """Test 2 detail: preferred_mode carried through."""
        params = MemoryPersonalizationParams(preferred_mode="spatial_pattern_recall")
        profile = _make_profile("memory", "medium", params)
        result = _adapt_memory(profile)
        self.assertEqual(result.preferred_mode, "spatial_pattern_recall")

    def test_palette_theme_mapped(self):
        """Test 2 detail: palette_theme carried through."""
        params = MemoryPersonalizationParams(palette_theme="geometric_shapes")
        profile = _make_profile("memory", "medium", params)
        result = _adapt_memory(profile)
        self.assertEqual(result.palette_theme, "geometric_shapes")

    def test_no_params_gives_none_fields(self):
        """Test 11: No typed_parameters -> all mapped fields are None."""
        profile = _make_profile("memory", "easy", None)
        result = _adapt_memory(profile)
        self.assertIsNone(result.preferred_mode)
        self.assertIsNone(result.palette_theme)

    def test_no_sequence_generated(self):
        """Test 12: No display_sequence, pattern, or answer fields in output."""
        profile = _make_profile("memory", "medium", MemoryPersonalizationParams())
        result = _adapt_memory(profile)
        self.assertFalse(hasattr(result, "display_sequence"))
        self.assertFalse(hasattr(result, "highlighted_cells"))
        self.assertFalse(hasattr(result, "proposed_answer"))
        self.assertFalse(hasattr(result, "content_payload"))

    def test_no_number_guessing_fields(self):
        """Test 2 and Phase 4.3 guard: no numeric memory fields introduced."""
        profile = _make_profile("memory", "medium", MemoryPersonalizationParams())
        result = _adapt_memory(profile)
        self.assertFalse(hasattr(result, "number_sequence"))
        self.assertFalse(hasattr(result, "pin_code"))
        self.assertFalse(hasattr(result, "digit"))

    def test_desired_duration_as_hint_only(self):
        """Test 16: desired_duration_seconds does not change difficulty."""
        profile = _make_profile("memory", "easy", MemoryPersonalizationParams(),
                                desired_duration_seconds=45)
        result = _adapt_memory(profile)
        self.assertEqual(result.desired_duration_seconds, 45)
        self.assertEqual(result.difficulty_level, "easy")

    def test_phase43_contract_no_math_fields(self):
        """Test 18: Memory output must not contain math-specific fields."""
        profile = _make_profile("memory", "medium", MemoryPersonalizationParams())
        result = _adapt_memory(profile)
        self.assertFalse(hasattr(result, "focus_topic"))
        self.assertFalse(hasattr(result, "preferred_operation"))
        self.assertFalse(hasattr(result, "operand_scale_preference"))

    def test_deterministic_output(self):
        """Test 23: Identical inputs produce identical outputs."""
        params = MemoryPersonalizationParams(
            preferred_mode="dynamic_spatial_path",
            palette_theme="emojis",
        )
        p1 = _make_profile("memory", "hard", params, desired_duration_seconds=60)
        p2 = _make_profile("memory", "hard", params, desired_duration_seconds=60)
        self.assertEqual(_adapt_memory(p1), _adapt_memory(p2))

    def test_adapt_profile_dispatches_to_memory(self):
        """Test 24: adapt_profile dispatches memory correctly."""
        profile = _make_profile("memory", "medium", MemoryPersonalizationParams())
        result = adapt_profile(profile)
        self.assertIsInstance(result, MemoryPersonalizationAdapterOutput)
        self.assertEqual(result.challenge_type, "memory")


class TestTongueTwisterAdapter(unittest.TestCase):
    """Tests 3, 6, 7, 12, 19, 21, 22, 23, 24 (tongue-twister slice)."""

    def test_returns_tongue_twister_adapter_output(self):
        """Test 3: tongue_twister profile -> TongueTwisterPersonalizationAdapterOutput."""
        params = TongueTwisterPersonalizationParams(
            target_sound_family="sibilants",
            theme_style="nature",
        )
        profile = _make_profile("tongue_twister", "medium", params)
        result = _adapt_tongue_twister(profile)
        self.assertIsInstance(result, TongueTwisterPersonalizationAdapterOutput)

    def test_challenge_type_preserved(self):
        """Test 6: challenge_type remains tongue_twister."""
        profile = _make_profile("tongue_twister", "easy", TongueTwisterPersonalizationParams())
        result = _adapt_tongue_twister(profile)
        self.assertEqual(result.challenge_type, "tongue_twister")

    def test_difficulty_preserved(self):
        """Test 7: difficulty_level preserved."""
        profile = _make_profile("tongue_twister", "hard", TongueTwisterPersonalizationParams())
        result = _adapt_tongue_twister(profile)
        self.assertEqual(result.difficulty_level, "hard")

    def test_target_sound_family_mapped(self):
        """Test 3 detail: target_sound_family carried through."""
        params = TongueTwisterPersonalizationParams(target_sound_family="plosives")
        profile = _make_profile("tongue_twister", "medium", params)
        result = _adapt_tongue_twister(profile)
        self.assertEqual(result.target_sound_family, "plosives")

    def test_theme_style_mapped(self):
        """Test 3 detail: theme_style carried through."""
        params = TongueTwisterPersonalizationParams(theme_style="animals")
        profile = _make_profile("tongue_twister", "easy", params)
        result = _adapt_tongue_twister(profile)
        self.assertEqual(result.theme_style, "animals")

    def test_no_passage_generated(self):
        """Test 12: No passage, sentence, or repetition fields in output."""
        profile = _make_profile("tongue_twister", "medium", TongueTwisterPersonalizationParams())
        result = _adapt_tongue_twister(profile)
        self.assertFalse(hasattr(result, "passage"))
        self.assertFalse(hasattr(result, "target_repetitions"))
        self.assertFalse(hasattr(result, "speaking_duration_seconds"))
        self.assertFalse(hasattr(result, "content_payload"))

    def test_desired_duration_as_hint_only(self):
        """Test 16: desired_duration_seconds does not change difficulty."""
        profile = _make_profile(
            "tongue_twister", "easy",
            TongueTwisterPersonalizationParams(),
            desired_duration_seconds=20,
        )
        result = _adapt_tongue_twister(profile)
        self.assertEqual(result.desired_duration_seconds, 20)
        self.assertEqual(result.difficulty_level, "easy")

    def test_phase44_contract_no_math_or_memory_fields(self):
        """Test 19: TT output must not contain math or memory fields."""
        profile = _make_profile("tongue_twister", "medium", TongueTwisterPersonalizationParams())
        result = _adapt_tongue_twister(profile)
        self.assertFalse(hasattr(result, "focus_topic"))
        self.assertFalse(hasattr(result, "preferred_mode"))
        self.assertFalse(hasattr(result, "palette_theme"))

    def test_no_params_gives_none_fields(self):
        """Test 11: No typed_parameters -> all mapped fields are None."""
        profile = _make_profile("tongue_twister", "easy", None)
        result = _adapt_tongue_twister(profile)
        self.assertIsNone(result.target_sound_family)
        self.assertIsNone(result.theme_style)

    def test_deterministic_output(self):
        """Test 23: Identical inputs produce identical outputs."""
        params = TongueTwisterPersonalizationParams(
            target_sound_family="nasals", theme_style="rhyme"
        )
        p1 = _make_profile("tongue_twister", "hard", params, desired_duration_seconds=30)
        p2 = _make_profile("tongue_twister", "hard", params, desired_duration_seconds=30)
        self.assertEqual(_adapt_tongue_twister(p1), _adapt_tongue_twister(p2))

    def test_adapt_profile_dispatches_to_tongue_twister(self):
        """Test 24: adapt_profile dispatches tongue_twister correctly."""
        profile = _make_profile("tongue_twister", "medium", TongueTwisterPersonalizationParams())
        result = adapt_profile(profile)
        self.assertIsInstance(result, TongueTwisterPersonalizationAdapterOutput)
        self.assertEqual(result.challenge_type, "tongue_twister")


class TestDanceAdapter(unittest.TestCase):
    """Tests 4, 6, 7, 12, 20, 21, 22, 23, 24 (dance slice)."""

    def test_returns_dance_adapter_output(self):
        """Test 4: dance profile -> DancePersonalizationAdapterOutput."""
        params = DancePersonalizationParams(movement_style="rhythm_groove", pacing="dynamic")
        profile = _make_profile("dance", "medium", params)
        result = _adapt_dance(profile)
        self.assertIsInstance(result, DancePersonalizationAdapterOutput)

    def test_challenge_type_preserved(self):
        """Test 6: challenge_type remains dance."""
        profile = _make_profile("dance", "easy", DancePersonalizationParams())
        result = _adapt_dance(profile)
        self.assertEqual(result.challenge_type, "dance")

    def test_difficulty_preserved(self):
        """Test 7: difficulty_level preserved."""
        profile = _make_profile("dance", "hard", DancePersonalizationParams())
        result = _adapt_dance(profile)
        self.assertEqual(result.difficulty_level, "hard")

    def test_movement_style_mapped(self):
        """Test 4 detail: movement_style carried through."""
        params = DancePersonalizationParams(movement_style="arm_raises")
        profile = _make_profile("dance", "medium", params)
        result = _adapt_dance(profile)
        self.assertEqual(result.movement_style, "arm_raises")

    def test_pacing_mapped(self):
        """Test 4 detail: pacing carried through."""
        params = DancePersonalizationParams(pacing="slow")
        profile = _make_profile("dance", "easy", params)
        result = _adapt_dance(profile)
        self.assertEqual(result.pacing, "slow")

    def test_no_routine_generated(self):
        """Tests 12 and 20: No routine, pose, or content fields in output."""
        profile = _make_profile("dance", "medium", DancePersonalizationParams())
        result = _adapt_dance(profile)
        self.assertFalse(hasattr(result, "routine"))
        self.assertFalse(hasattr(result, "poses"))
        self.assertFalse(hasattr(result, "choreography"))
        self.assertFalse(hasattr(result, "content_payload"))

    def test_no_ai_content_fields(self):
        """Test 20: Dance output is procedural only, no AI-generated fields."""
        profile = _make_profile("dance", "medium", DancePersonalizationParams())
        result = _adapt_dance(profile)
        self.assertFalse(hasattr(result, "generated_routine"))
        self.assertFalse(hasattr(result, "llm_response"))

    def test_desired_duration_as_hint_only(self):
        """Test 16: desired_duration_seconds does not change difficulty."""
        profile = _make_profile("dance", "easy", DancePersonalizationParams(),
                                desired_duration_seconds=90)
        result = _adapt_dance(profile)
        self.assertEqual(result.desired_duration_seconds, 90)
        self.assertEqual(result.difficulty_level, "easy")

    def test_no_params_gives_none_fields(self):
        """Test 11: No typed_parameters -> all mapped fields are None."""
        profile = _make_profile("dance", "medium", None)
        result = _adapt_dance(profile)
        self.assertIsNone(result.movement_style)
        self.assertIsNone(result.pacing)

    def test_deterministic_output(self):
        """Test 23: Identical inputs produce identical outputs."""
        params = DancePersonalizationParams(movement_style="step_touch", pacing="moderate")
        p1 = _make_profile("dance", "hard", params, desired_duration_seconds=60)
        p2 = _make_profile("dance", "hard", params, desired_duration_seconds=60)
        self.assertEqual(_adapt_dance(p1), _adapt_dance(p2))

    def test_adapt_profile_dispatches_to_dance(self):
        """Test 24: adapt_profile dispatches dance correctly."""
        profile = _make_profile("dance", "medium", DancePersonalizationParams())
        result = adapt_profile(profile)
        self.assertIsInstance(result, DancePersonalizationAdapterOutput)
        self.assertEqual(result.challenge_type, "dance")


class TestPushUpAdapter(unittest.TestCase):
    """Tests 5, 6, 7, 12, 20, 21, 22, 23, 24 (push-up slice)."""

    def test_returns_pushup_adapter_output(self):
        """Test 5: push_ups profile -> PushUpPersonalizationAdapterOutput."""
        params = PushUpPersonalizationParams(
            cadence_tempo="tempo_pause", target_rep_styling="tier_max"
        )
        profile = _make_profile("push_ups", "medium", params)
        result = _adapt_push_ups(profile)
        self.assertIsInstance(result, PushUpPersonalizationAdapterOutput)

    def test_challenge_type_preserved(self):
        """Test 6: challenge_type remains push_ups."""
        profile = _make_profile("push_ups", "easy", PushUpPersonalizationParams())
        result = _adapt_push_ups(profile)
        self.assertEqual(result.challenge_type, "push_ups")

    def test_difficulty_preserved(self):
        """Test 7: difficulty_level preserved."""
        profile = _make_profile("push_ups", "hard", PushUpPersonalizationParams())
        result = _adapt_push_ups(profile)
        self.assertEqual(result.difficulty_level, "hard")

    def test_cadence_tempo_mapped(self):
        """Test 5 detail: cadence_tempo carried through."""
        params = PushUpPersonalizationParams(cadence_tempo="steady")
        profile = _make_profile("push_ups", "medium", params)
        result = _adapt_push_ups(profile)
        self.assertEqual(result.cadence_tempo, "steady")

    def test_target_rep_styling_mapped(self):
        """Test 5 detail: target_rep_styling carried through."""
        params = PushUpPersonalizationParams(target_rep_styling="tier_min")
        profile = _make_profile("push_ups", "easy", params)
        result = _adapt_push_ups(profile)
        self.assertEqual(result.target_rep_styling, "tier_min")

    def test_no_rep_count_generated(self):
        """Tests 12 and 20: No actual rep_count, routine, or content fields."""
        profile = _make_profile("push_ups", "medium", PushUpPersonalizationParams())
        result = _adapt_push_ups(profile)
        self.assertFalse(hasattr(result, "rep_count"))
        self.assertFalse(hasattr(result, "repetitions"))
        self.assertFalse(hasattr(result, "execution_plan"))
        self.assertFalse(hasattr(result, "content_payload"))

    def test_no_ai_content_fields(self):
        """Test 20: Push-up output is procedural only, no AI-generated fields."""
        profile = _make_profile("push_ups", "medium", PushUpPersonalizationParams())
        result = _adapt_push_ups(profile)
        self.assertFalse(hasattr(result, "generated_plan"))
        self.assertFalse(hasattr(result, "llm_response"))

    def test_desired_duration_as_hint_only(self):
        """Test 16: desired_duration_seconds does not change difficulty."""
        profile = _make_profile("push_ups", "easy", PushUpPersonalizationParams(),
                                desired_duration_seconds=120)
        result = _adapt_push_ups(profile)
        self.assertEqual(result.desired_duration_seconds, 120)
        self.assertEqual(result.difficulty_level, "easy")

    def test_no_params_gives_none_fields(self):
        """Test 11: No typed_parameters -> all mapped fields are None."""
        profile = _make_profile("push_ups", "medium", None)
        result = _adapt_push_ups(profile)
        self.assertIsNone(result.cadence_tempo)
        self.assertIsNone(result.target_rep_styling)

    def test_deterministic_output(self):
        """Test 23: Identical inputs produce identical outputs."""
        params = PushUpPersonalizationParams(
            cadence_tempo="standard", target_rep_styling="tier_median"
        )
        p1 = _make_profile("push_ups", "hard", params, desired_duration_seconds=45)
        p2 = _make_profile("push_ups", "hard", params, desired_duration_seconds=45)
        self.assertEqual(_adapt_push_ups(p1), _adapt_push_ups(p2))

    def test_adapt_profile_dispatches_to_push_ups(self):
        """Test 24: adapt_profile dispatches push_ups correctly."""
        profile = _make_profile("push_ups", "medium", PushUpPersonalizationParams())
        result = adapt_profile(profile)
        self.assertIsInstance(result, PushUpPersonalizationAdapterOutput)
        self.assertEqual(result.challenge_type, "push_ups")


class TestTypeAndDifficultyImmutability(unittest.TestCase):
    """Tests 8, 9, 10: wrong model, forbidden type, invalid difficulty."""

    def test_wrong_param_model_math_receives_memory(self):
        """Test 8: math adapter with MemoryPersonalizationParams raises error."""
        mem_params = MemoryPersonalizationParams(preferred_mode="visual_sequence")
        profile = _make_profile("math", "medium", MathPersonalizationParams())
        object.__setattr__(profile, "typed_parameters", mem_params)
        with self.assertRaises(AdapterParameterMismatchError):
            _adapt_math(profile)

    def test_wrong_param_model_memory_receives_math(self):
        """Test 8: memory adapter with MathPersonalizationParams raises error."""
        math_params = MathPersonalizationParams(preferred_operation="addition")
        profile = _make_profile("memory", "medium", MemoryPersonalizationParams())
        object.__setattr__(profile, "typed_parameters", math_params)
        with self.assertRaises(AdapterParameterMismatchError):
            _adapt_memory(profile)

    def test_wrong_param_model_tongue_twister_receives_dance(self):
        """Test 8: tongue_twister adapter with DancePersonalizationParams raises error."""
        dance_params = DancePersonalizationParams(pacing="slow")
        profile = _make_profile("tongue_twister", "easy", TongueTwisterPersonalizationParams())
        object.__setattr__(profile, "typed_parameters", dance_params)
        with self.assertRaises(AdapterParameterMismatchError):
            _adapt_tongue_twister(profile)

    def test_wrong_param_model_dance_receives_pushup(self):
        """Test 8: dance adapter with PushUpPersonalizationParams raises error."""
        pushup_params = PushUpPersonalizationParams(cadence_tempo="steady")
        profile = _make_profile("dance", "medium", DancePersonalizationParams())
        object.__setattr__(profile, "typed_parameters", pushup_params)
        with self.assertRaises(AdapterParameterMismatchError):
            _adapt_dance(profile)

    def test_wrong_param_model_pushup_receives_math(self):
        """Test 8: push_ups adapter with MathPersonalizationParams raises error."""
        math_params = MathPersonalizationParams(focus_topic="cooking")
        profile = _make_profile("push_ups", "easy", PushUpPersonalizationParams())
        object.__setattr__(profile, "typed_parameters", math_params)
        with self.assertRaises(AdapterParameterMismatchError):
            _adapt_push_ups(profile)

    def test_forbidden_challenge_type_rejected(self):
        """Test 9: Forbidden challenge type raises AdapterTypeError."""
        from backend.app.core.constants import FORBIDDEN_CHALLENGE_TYPES
        profile = _make_profile("math", "easy", MathPersonalizationParams())
        for forbidden in FORBIDDEN_CHALLENGE_TYPES:
            object.__setattr__(profile, "challenge_type", forbidden)
            with self.assertRaises(AdapterTypeError):
                _validate_type_and_difficulty(profile)

    def test_unknown_challenge_type_rejected(self):
        """Test 9 unknown: Unknown challenge type raises AdapterTypeError."""
        profile = _make_profile("math", "easy", MathPersonalizationParams())
        for unknown in ("trivia", "quiz", "yoga", "number_guessing_extended", ""):
            object.__setattr__(profile, "challenge_type", unknown)
            with self.assertRaises(AdapterTypeError):
                _validate_type_and_difficulty(profile)

    def test_invalid_difficulty_rejected(self):
        """Test 10: Invalid difficulty level raises AdapterDifficultyError."""
        profile = _make_profile("math", "easy", MathPersonalizationParams())
        for bad_diff in ("adaptive", "extreme", "beginner", "ultra", "", "HARD"):
            object.__setattr__(profile, "difficulty_level", bad_diff)
            with self.assertRaises(AdapterDifficultyError):
                _validate_type_and_difficulty(profile)

    def test_difficulty_not_mutated_by_duration(self):
        """Test 16: Adapter never upgrades or downgrades difficulty based on duration."""
        all_cases = [
            ("math", MathPersonalizationParams()),
            ("memory", MemoryPersonalizationParams()),
            ("tongue_twister", TongueTwisterPersonalizationParams()),
            ("dance", DancePersonalizationParams()),
            ("push_ups", PushUpPersonalizationParams()),
        ]
        for ctype, params in all_cases:
            for diff in ("easy", "medium", "hard"):
                for dur in (5, 15, 60, 120, 300):
                    profile = _make_profile(ctype, diff, params, desired_duration_seconds=dur)
                    result = adapt_profile(profile)
                    self.assertEqual(
                        result.difficulty_level, diff,
                        f"Difficulty mutated for {ctype} dur={dur}",
                    )


class TestNoForbiddenSideEffects(unittest.TestCase):
    """Tests 13, 14, 15: No LLM, no DB, no randomization."""

    def test_no_network_imports_in_adapter_module(self):
        """Test 13: Adapter module must not import network/AI libraries."""
        import backend.app.services.genai.personalization_adapters as adapter_mod
        source = inspect.getsource(adapter_mod)
        forbidden_imports = [
            "import requests",
            "import httpx",
            "import aiohttp",
            "import gemini",
            "import google.generativeai",
            "import openai",
            "import anthropic",
            "import langchain",
            "GenAIService",
            "GeminiProvider",
            "generate_challenge_content",
        ]
        for forbidden in forbidden_imports:
            self.assertNotIn(
                forbidden, source,
                f"Adapter module must not reference '{forbidden}'.",
            )

    def test_no_db_imports_in_adapter_module(self):
        """Test 14: Adapter module must not import ORM or DB libraries."""
        import backend.app.services.genai.personalization_adapters as adapter_mod
        source = inspect.getsource(adapter_mod)
        forbidden_db = [
            "sqlalchemy",
            "alembic",
            "from backend.app.db",
            "from backend.app.models",
            "import orm",
            "get_db",
        ]
        for forbidden in forbidden_db:
            self.assertNotIn(
                forbidden, source,
                f"Adapter module must not reference DB symbol '{forbidden}'.",
            )

    def test_no_random_imports_in_adapter_module(self):
        """Test 15: Adapter module must not import randomization utilities."""
        import backend.app.services.genai.personalization_adapters as adapter_mod
        source = inspect.getsource(adapter_mod)
        for forbidden in ("import random", "import uuid", "import secrets"):
            self.assertNotIn(
                forbidden, source,
                f"Adapter module must not use '{forbidden}'.",
            )

    def test_no_timestamp_usage_in_adapter_module(self):
        """Test 15 timestamps: Adapter must not use runtime timestamps."""
        import backend.app.services.genai.personalization_adapters as adapter_mod
        source = inspect.getsource(adapter_mod)
        self.assertNotIn("datetime.now", source)
        self.assertNotIn("time.time()", source)

    def test_repeated_calls_produce_same_output(self):
        """Test 15 determinism: Same profile produces same result on repeated calls."""
        params = MathPersonalizationParams(focus_topic="astronomy", preferred_operation="addition")
        profile = _make_profile("math", "hard", params, desired_duration_seconds=30)
        results = [_adapt_math(profile) for _ in range(5)]
        for r in results[1:]:
            self.assertEqual(r, results[0])


class TestAllFiveTypesAreCovered(unittest.TestCase):
    """Test 24: All five canonical challenge types produce distinct, correct outputs."""

    def test_all_five_types_dispatch_correctly(self):
        """Test 24: adapt_profile dispatches all five challenge types."""
        cases = [
            ("math", MathPersonalizationParams(), MathPersonalizationAdapterOutput),
            ("memory", MemoryPersonalizationParams(), MemoryPersonalizationAdapterOutput),
            (
                "tongue_twister",
                TongueTwisterPersonalizationParams(),
                TongueTwisterPersonalizationAdapterOutput,
            ),
            ("dance", DancePersonalizationParams(), DancePersonalizationAdapterOutput),
            ("push_ups", PushUpPersonalizationParams(), PushUpPersonalizationAdapterOutput),
        ]
        for ctype, params, expected_cls in cases:
            with self.subTest(challenge_type=ctype):
                profile = _make_profile(ctype, "medium", params)
                result = adapt_profile(profile)
                self.assertIsInstance(result, expected_cls)
                self.assertEqual(result.challenge_type, ctype)
                self.assertEqual(result.difficulty_level, "medium")

    def test_all_five_types_no_cross_contamination(self):
        """Test 24: Each type output only contains its own type-specific fields."""
        math_result = _adapt_math(_make_profile("math", "easy", MathPersonalizationParams()))
        memory_result = _adapt_memory(
            _make_profile("memory", "easy", MemoryPersonalizationParams())
        )
        tt_result = _adapt_tongue_twister(
            _make_profile("tongue_twister", "easy", TongueTwisterPersonalizationParams())
        )
        dance_result = _adapt_dance(_make_profile("dance", "easy", DancePersonalizationParams()))
        pu_result = _adapt_push_ups(
            _make_profile("push_ups", "easy", PushUpPersonalizationParams())
        )

        self.assertFalse(hasattr(math_result, "preferred_mode"))
        self.assertFalse(hasattr(memory_result, "focus_topic"))
        self.assertFalse(hasattr(tt_result, "movement_style"))
        self.assertFalse(hasattr(dance_result, "cadence_tempo"))
        self.assertFalse(hasattr(pu_result, "target_sound_family"))


class TestStrictTypedOutputs(unittest.TestCase):
    """Tests 21 and 22: All outputs are strictly typed Pydantic models, no Dict[str, Any]."""

    def test_math_output_model_fields_are_typed(self):
        """Test 21 and 22: MathPersonalizationAdapterOutput has typed model fields."""
        profile = _make_profile("math", "medium",
                                MathPersonalizationParams(focus_topic="cooking"))
        result = _adapt_math(profile)
        self.assertIn("challenge_type", type(result).model_fields)
        self.assertIn("difficulty_level", type(result).model_fields)
        self.assertIn("focus_topic", type(result).model_fields)
        self.assertNotIsInstance(result, dict)

    def test_memory_output_model_fields_are_typed(self):
        """Test 21 and 22: MemoryPersonalizationAdapterOutput has typed model fields."""
        profile = _make_profile("memory", "medium", MemoryPersonalizationParams())
        result = _adapt_memory(profile)
        self.assertIn("preferred_mode", type(result).model_fields)
        self.assertIn("palette_theme", type(result).model_fields)
        self.assertNotIsInstance(result, dict)

    def test_tongue_twister_output_model_fields_are_typed(self):
        """Test 21 and 22: TongueTwisterPersonalizationAdapterOutput has typed model fields."""
        profile = _make_profile("tongue_twister", "easy", TongueTwisterPersonalizationParams())
        result = _adapt_tongue_twister(profile)
        self.assertIn("target_sound_family", type(result).model_fields)
        self.assertIn("theme_style", type(result).model_fields)
        self.assertNotIsInstance(result, dict)

    def test_dance_output_model_fields_are_typed(self):
        """Test 21 and 22: DancePersonalizationAdapterOutput has typed model fields."""
        profile = _make_profile("dance", "easy", DancePersonalizationParams())
        result = _adapt_dance(profile)
        self.assertIn("movement_style", type(result).model_fields)
        self.assertIn("pacing", type(result).model_fields)
        self.assertNotIsInstance(result, dict)

    def test_pushup_output_model_fields_are_typed(self):
        """Test 21 and 22: PushUpPersonalizationAdapterOutput has typed model fields."""
        profile = _make_profile("push_ups", "easy", PushUpPersonalizationParams())
        result = _adapt_push_ups(profile)
        self.assertIn("cadence_tempo", type(result).model_fields)
        self.assertIn("target_rep_styling", type(result).model_fields)
        self.assertNotIsInstance(result, dict)


if __name__ == "__main__":
    unittest.main(verbosity=2)
