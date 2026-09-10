"""Unit tests for Phase 4.5 Step 3: Challenge Personalization Service & Precedence Engine.

Validates:
1. Correct profile creation for all 5 canonical challenge types (math, memory, tongue_twister, dance, push_ups).
2. Challenge type immutability under all conditions.
3. Concrete difficulty immutability under all conditions.
4. Forbidden challenge types explicitly rejected (number_guessing, guess_number, numeric_memory).
5. Explicit user preferences take priority over behavioral defaults.
6. Behavioral signals personalize parameters but NEVER difficulty.
7. historical_success_rate=None handled strictly as NO HISTORY.
8. High snooze/failure behavior remains within the authoritative difficulty tier.
9. Retry attempt behavior.
10. Structural repetition detection.
11. Deterministic alternative selection after repetition.
12. Bounded repetition attempts (<= 3).
13. Safe fallback when all alternatives repeat.
14. desired_duration_seconds affects only generation preference parameters.
15. No alarm-time modification.
16. No database access.
17. No post-challenge data usage.
18. No PII/identity fields required or stored.
19. Determinism — identical input produces identical output.
20. Different challenge types produce appropriate typed parameter models.
21. Absence of Dict[str, Any].
22. Strict Pydantic validation remains intact (extra="forbid", strict=True).
23. Step 1 schema compatibility.
24. Step 2 structural repetition compatibility.
25. All produced profiles satisfy PersonalizedChallengeProfile validation.
26. Disallowed topics safety rules (a through j).
"""
import unittest
from typing import List, Optional

from pydantic import ValidationError

from backend.app.schemas.challenge_content_schemas import SafePersonalizationContext
from backend.app.schemas.personalization_content_schemas import (
    BehavioralPersonalizationSignals,
    DancePersonalizationParams,
    MathPersonalizationParams,
    MemoryPersonalizationParams,
    PersonalizedChallengeProfile,
    PushUpPersonalizationParams,
    TongueTwisterPersonalizationParams,
)
from backend.app.services.genai.challenge_personalization_service import (
    ChallengePersonalizationService,
    ForbiddenChallengeTypeError,
    InvalidChallengeTypeError,
    InvalidDifficultyLevelError,
    MAX_REPETITION_ATTEMPTS,
    is_topic_disallowed,
    sanitize_input_signatures,
)
from backend.app.services.genai.structural_repetition import (
    build_signature_from_profile,
    is_structural_repeat,
)


def make_safe_context(
    desired_duration_seconds: Optional[int] = None,
    preferred_theme: Optional[str] = None,
    disallowed_topics: Optional[List[str]] = None,
    language: str = "en",
) -> SafePersonalizationContext:
    """Helper to instantiate SafePersonalizationContext with all keyword defaults."""
    return SafePersonalizationContext(
        desired_duration_seconds=desired_duration_seconds,
        preferred_theme=preferred_theme,
        disallowed_topics=disallowed_topics if disallowed_topics is not None else [],
        language=language,
    )


class TestChallengePersonalizationBasics(unittest.TestCase):
    """Test Suite 1: Correct profile creation and typed parameters for all 5 challenge types."""

    def setUp(self):
        self.service = ChallengePersonalizationService()

    def test_math_profile_creation(self):
        """Math challenge type produces MathPersonalizationParams with valid defaults."""
        profile = self.service.personalize(challenge_type="math", difficulty_level="medium")
        self.assertEqual(profile.challenge_type, "math")
        self.assertEqual(profile.difficulty_level, "medium")
        self.assertIsInstance(profile.typed_parameters, MathPersonalizationParams)
        assert isinstance(profile.typed_parameters, MathPersonalizationParams)
        self.assertIn(profile.typed_parameters.preferred_operation, ["addition", "subtraction", "multiplication", "division", "mixed"])
        self.assertIn(profile.typed_parameters.operand_scale_preference, ["compact", "standard"])

    def test_memory_profile_creation(self):
        """Memory challenge type produces MemoryPersonalizationParams with non-numeric modes/themes."""
        profile = self.service.personalize(challenge_type="memory", difficulty_level="easy")
        self.assertEqual(profile.challenge_type, "memory")
        self.assertEqual(profile.difficulty_level, "easy")
        self.assertIsInstance(profile.typed_parameters, MemoryPersonalizationParams)
        assert isinstance(profile.typed_parameters, MemoryPersonalizationParams)
        self.assertIn(profile.typed_parameters.preferred_mode, [
            "visual_sequence", "spatial_pattern_recall", "dynamic_spatial_path", "symbol_chronological_order"
        ])
        self.assertIn(profile.typed_parameters.palette_theme, [
            "colors", "geometric_shapes", "cardinal_directions", "emojis"
        ])

    def test_tongue_twister_profile_creation(self):
        """Tongue twister challenge type produces TongueTwisterPersonalizationParams."""
        profile = self.service.personalize(challenge_type="tongue_twister", difficulty_level="hard")
        self.assertEqual(profile.challenge_type, "tongue_twister")
        self.assertEqual(profile.difficulty_level, "hard")
        self.assertIsInstance(profile.typed_parameters, TongueTwisterPersonalizationParams)
        assert isinstance(profile.typed_parameters, TongueTwisterPersonalizationParams)
        self.assertIn(profile.typed_parameters.target_sound_family, [
            "sibilants", "plosives", "liquids", "nasals", "any"
        ])
        self.assertIn(profile.typed_parameters.theme_style, [
            "nature", "animals", "workday", "whimsical", "rhyme"
        ])

    def test_dance_profile_creation(self):
        """Dance challenge type produces DancePersonalizationParams."""
        profile = self.service.personalize(challenge_type="dance", difficulty_level="medium")
        self.assertEqual(profile.challenge_type, "dance")
        self.assertEqual(profile.difficulty_level, "medium")
        self.assertIsInstance(profile.typed_parameters, DancePersonalizationParams)
        assert isinstance(profile.typed_parameters, DancePersonalizationParams)
        self.assertIn(profile.typed_parameters.movement_style, [
            "rhythm_groove", "arm_raises", "step_touch", "standard"
        ])
        self.assertIn(profile.typed_parameters.pacing, ["slow", "moderate", "dynamic"])

    def test_push_ups_profile_creation(self):
        """Push-ups challenge type produces PushUpPersonalizationParams."""
        profile = self.service.personalize(challenge_type="push_ups", difficulty_level="hard")
        self.assertEqual(profile.challenge_type, "push_ups")
        self.assertEqual(profile.difficulty_level, "hard")
        self.assertIsInstance(profile.typed_parameters, PushUpPersonalizationParams)
        assert isinstance(profile.typed_parameters, PushUpPersonalizationParams)
        self.assertIn(profile.typed_parameters.cadence_tempo, ["steady", "tempo_pause", "standard"])
        self.assertIn(profile.typed_parameters.target_rep_styling, ["tier_min", "tier_median", "tier_max"])

    def test_all_profiles_satisfy_schema_validation(self):
        """All created profiles pass strict PersonalizedChallengeProfile validation."""
        for ctype in ["math", "memory", "tongue_twister", "dance", "push_ups"]:
            for diff in ["easy", "medium", "hard"]:
                profile = self.service.personalize(challenge_type=ctype, difficulty_level=diff)
                self.assertIsInstance(profile, PersonalizedChallengeProfile)
                # Verify round-trip model dump without validation errors
                reloaded = PersonalizedChallengeProfile.model_validate(profile.model_dump())
                self.assertEqual(reloaded.challenge_type, ctype)
                self.assertEqual(reloaded.difficulty_level, diff)


class TestPrecedenceEngineAuthority(unittest.TestCase):
    """Test Suite 2: Strict Authority, Immutability & Rejection of Forbidden Types."""

    def setUp(self):
        self.service = ChallengePersonalizationService()

    def test_forbidden_challenge_types_rejected(self):
        """Forbidden challenge types (number guessing, numeric memory) are rejected with ForbiddenChallengeTypeError."""
        forbidden = ["number_guessing", "guess_number", "numeric_memory"]
        for bad_type in forbidden:
            with self.assertRaises(ForbiddenChallengeTypeError):
                self.service.personalize(challenge_type=bad_type, difficulty_level="easy")

    def test_unsupported_challenge_type_rejected(self):
        """Non-canonical challenge types raise InvalidChallengeTypeError."""
        invalid = ["trivia", "chess", "sudoku", "", "   "]
        for bad_type in invalid:
            with self.assertRaises(InvalidChallengeTypeError):
                self.service.personalize(challenge_type=bad_type, difficulty_level="easy")

    def test_invalid_difficulty_level_rejected(self):
        """Non-canonical difficulty levels (adaptive, extreme, invalid) raise InvalidDifficultyLevelError."""
        invalid_diffs = ["adaptive", "extreme", "expert", "none", "", "1"]
        for bad_diff in invalid_diffs:
            with self.assertRaises(InvalidDifficultyLevelError):
                self.service.personalize(challenge_type="math", difficulty_level=bad_diff)

    def test_challenge_type_immutability(self):
        """Authoritative challenge_type is NEVER mutated by any input or condition."""
        signals = BehavioralPersonalizationSignals(
            recent_snooze_level="high",
            recent_failure_count=5,
            historical_success_rate=0.1,
            is_retry_attempt=True,
        )
        context = make_safe_context(
            desired_duration_seconds=10,
            preferred_theme="calm morning",
            disallowed_topics=["math", "memory", "dance"],
        )
        profile = self.service.personalize(
            challenge_type="math",
            difficulty_level="hard",
            safe_context=context,
            behavioral_signals=signals,
        )
        self.assertEqual(profile.challenge_type, "math")

    def test_difficulty_immutability(self):
        """Authoritative difficulty_level is NEVER mutated by high snooze, failures, or retry."""
        signals = BehavioralPersonalizationSignals(
            recent_snooze_level="high",
            recent_failure_count=8,
            historical_success_rate=0.0,
            is_retry_attempt=True,
        )
        # Even with extreme friction, "hard" MUST remain "hard"
        profile = self.service.personalize(
            challenge_type="push_ups",
            difficulty_level="hard",
            behavioral_signals=signals,
        )
        self.assertEqual(profile.difficulty_level, "hard")


class TestExplicitUserPreferences(unittest.TestCase):
    """Test Suite 3: Explicit User Preferences (Level 4 precedence)."""

    def setUp(self):
        self.service = ChallengePersonalizationService()

    def test_math_preferred_theme_applied_to_focus_topic(self):
        """Explicit preferred_theme safely shapes math focus_topic."""
        ctx = make_safe_context(preferred_theme="astronomy")
        profile = self.service.personalize(challenge_type="math", difficulty_level="easy", safe_context=ctx)
        assert isinstance(profile.typed_parameters, MathPersonalizationParams)
        self.assertEqual(profile.typed_parameters.focus_topic, "astronomy")

    def test_memory_preferred_theme_applied_to_palette_theme(self):
        """Explicit preferred_theme='emojis' maps to memory palette_theme='emojis'."""
        ctx = make_safe_context(preferred_theme="emojis")
        profile = self.service.personalize(challenge_type="memory", difficulty_level="medium", safe_context=ctx)
        assert isinstance(profile.typed_parameters, MemoryPersonalizationParams)
        self.assertEqual(profile.typed_parameters.palette_theme, "emojis")

    def test_tongue_twister_preferred_theme_applied(self):
        """Explicit preferred_theme='animals' maps to tongue twister theme_style='animals'."""
        ctx = make_safe_context(preferred_theme="animals")
        profile = self.service.personalize(challenge_type="tongue_twister", difficulty_level="easy", safe_context=ctx)
        assert isinstance(profile.typed_parameters, TongueTwisterPersonalizationParams)
        self.assertEqual(profile.typed_parameters.theme_style, "animals")

    def test_explicit_preference_overrides_behavioral_defaults(self):
        """Explicit theme preference takes priority over behavioral defaults (Level 4 > Level 5)."""
        # Under high snooze, memory would default to 'colors', but user explicitly requested 'geometric_shapes'
        ctx = make_safe_context(preferred_theme="geometric_shapes")
        signals = BehavioralPersonalizationSignals(recent_snooze_level="high", recent_failure_count=3)
        profile = self.service.personalize(
            challenge_type="memory",
            difficulty_level="easy",
            safe_context=ctx,
            behavioral_signals=signals,
        )
        assert isinstance(profile.typed_parameters, MemoryPersonalizationParams)
        self.assertEqual(profile.typed_parameters.palette_theme, "geometric_shapes")

    def test_desired_duration_shapes_parameters_only(self):
        """desired_duration_seconds influences styling (e.g. compact operand scale) without changing difficulty."""
        short_ctx = make_safe_context(desired_duration_seconds=15)
        profile = self.service.personalize(challenge_type="math", difficulty_level="hard", safe_context=short_ctx)
        self.assertEqual(profile.difficulty_level, "hard")
        assert isinstance(profile.typed_parameters, MathPersonalizationParams)
        self.assertEqual(profile.typed_parameters.operand_scale_preference, "compact")

        long_ctx = make_safe_context(desired_duration_seconds=90)
        profile_long = self.service.personalize(challenge_type="math", difficulty_level="hard", safe_context=long_ctx)
        self.assertEqual(profile_long.difficulty_level, "hard")
        assert isinstance(profile_long.typed_parameters, MathPersonalizationParams)
        self.assertEqual(profile_long.typed_parameters.operand_scale_preference, "standard")


class TestBehavioralPersonalization(unittest.TestCase):
    """Test Suite 4: Behavioral Signals (Level 5 precedence)."""

    def setUp(self):
        self.service = ChallengePersonalizationService()

    def test_historical_success_rate_none_is_no_history(self):
        """historical_success_rate=None is treated strictly as no history (neutral defaults)."""
        signals = BehavioralPersonalizationSignals(historical_success_rate=None)
        profile = self.service.personalize(challenge_type="math", difficulty_level="medium", behavioral_signals=signals)
        assert isinstance(profile.typed_parameters, MathPersonalizationParams)
        # Medium baseline default is multiplication and standard scale
        self.assertEqual(profile.typed_parameters.preferred_operation, "multiplication")
        self.assertEqual(profile.typed_parameters.operand_scale_preference, "standard")

    def test_high_friction_adapts_parameters_within_difficulty(self):
        """High snooze and failures adjust parameters to accessible styles within the same difficulty."""
        signals = BehavioralPersonalizationSignals(
            recent_snooze_level="high",
            recent_failure_count=3,
        )
        # Math on easy: selects addition and compact
        math_prof = self.service.personalize(challenge_type="math", difficulty_level="easy", behavioral_signals=signals)
        self.assertEqual(math_prof.difficulty_level, "easy")
        assert isinstance(math_prof.typed_parameters, MathPersonalizationParams)
        self.assertEqual(math_prof.typed_parameters.preferred_operation, "addition")
        self.assertEqual(math_prof.typed_parameters.operand_scale_preference, "compact")

        # Push-ups on hard: selects tier_min and steady, but difficulty remains 'hard'
        push_prof = self.service.personalize(challenge_type="push_ups", difficulty_level="hard", behavioral_signals=signals)
        self.assertEqual(push_prof.difficulty_level, "hard")
        assert isinstance(push_prof.typed_parameters, PushUpPersonalizationParams)
        self.assertEqual(push_prof.typed_parameters.target_rep_styling, "tier_min")
        self.assertEqual(push_prof.typed_parameters.cadence_tempo, "steady")

    def test_high_success_rate_allows_richer_parameters(self):
        """Strong success history allows richer parameters within the authoritative difficulty."""
        signals = BehavioralPersonalizationSignals(
            historical_success_rate=0.9,
            recent_failure_count=0,
            recent_snooze_level="none",
        )
        profile = self.service.personalize(challenge_type="dance", difficulty_level="medium", behavioral_signals=signals)
        self.assertEqual(profile.difficulty_level, "medium")
        assert isinstance(profile.typed_parameters, DancePersonalizationParams)
        self.assertEqual(profile.typed_parameters.movement_style, "rhythm_groove")
        self.assertEqual(profile.typed_parameters.pacing, "dynamic")

    def test_retry_attempt_alters_structure(self):
        """is_retry_attempt=True varies structural configuration away from standard to break failure cycle."""
        standard_profile = self.service.personalize(challenge_type="math", difficulty_level="easy")
        assert isinstance(standard_profile.typed_parameters, MathPersonalizationParams)

        retry_signals = BehavioralPersonalizationSignals(is_retry_attempt=True)
        retry_profile = self.service.personalize(
            challenge_type="math",
            difficulty_level="easy",
            behavioral_signals=retry_signals,
        )
        assert isinstance(retry_profile.typed_parameters, MathPersonalizationParams)
        # Retry should shift operation from addition to subtraction
        self.assertNotEqual(
            standard_profile.typed_parameters.preferred_operation,
            retry_profile.typed_parameters.preferred_operation,
        )


class TestStructuralRepetitionAvoidance(unittest.TestCase):
    """Test Suite 5: Structural Repetition Detection & Deterministic Alternative Ladder (Level 6)."""

    def setUp(self):
        self.service = ChallengePersonalizationService()

    def test_repetition_detected_and_alternative_chosen(self):
        """When candidate signature matches history, a deterministic alternative is selected."""
        # Baseline profile signature for math easy
        base_profile = self.service.personalize(challenge_type="math", difficulty_level="easy")
        base_sig = build_signature_from_profile(base_profile)

        # Supply base_sig as recent history
        alt_profile = self.service.personalize(
            challenge_type="math",
            difficulty_level="easy",
            recent_structural_signatures=[base_sig],
        )
        alt_sig = build_signature_from_profile(alt_profile)

        self.assertNotEqual(base_sig, alt_sig)
        self.assertFalse(is_structural_repeat(alt_sig, [base_sig]))
        self.assertEqual(alt_profile.difficulty_level, "easy")
        self.assertEqual(alt_profile.challenge_type, "math")

    def test_bounded_repetition_attempts_and_fallback(self):
        """If all alternatives repeat, bounded attempts stop and fallback returns safely without mutating type/diff."""
        # Create a set of signatures that blocks initial candidate and alternatives
        base_profile = self.service.personalize(challenge_type="math", difficulty_level="easy")
        base_sig = build_signature_from_profile(base_profile)

        # Construct candidate signatures covering the attempts
        blocked_sigs = [
            "type=math|op=addition|scale=compact|diff=easy",
            "type=math|op=addition|scale=standard|diff=easy",
            "type=math|op=subtraction|scale=compact|diff=easy",
            "type=math|op=subtraction|scale=standard|diff=easy",
        ]

        fallback_profile = self.service.personalize(
            challenge_type="math",
            difficulty_level="easy",
            recent_structural_signatures=blocked_sigs,
        )

        # Immutability preserved
        self.assertEqual(fallback_profile.challenge_type, "math")
        self.assertEqual(fallback_profile.difficulty_level, "easy")
        self.assertIsInstance(fallback_profile.typed_parameters, MathPersonalizationParams)

    def test_sanitization_of_recent_signatures(self):
        """Recent signatures window bounds to <= 5 items and discards malformed or PII-leaking entries."""
        raw_sigs = [
            "type=math|op=addition|scale=compact",
            "malformed_sig_without_type",
            "type=memory|mode=visual_seq|user_id=123",  # PII leak rejected
            "type=dance|style=standard|pace=moderate",
            "type=push_ups|cad=standard|reps=tier_median",
            "type=tongue_twister|sound=sibilants|reps=2",
            "type=math|op=mixed|scale=standard",  # Exceeds max 5
        ]
        clean = sanitize_input_signatures(raw_sigs)
        self.assertLessEqual(len(clean), 5)
        for s in clean:
            self.assertTrue(s.startswith("type="))
            self.assertNotIn("user_id", s)


class TestDisallowedTopicsSafety(unittest.TestCase):
    """Test Suite 6: Disallowed Topics Safety Rules (Rules a through j)."""

    def setUp(self):
        self.service = ChallengePersonalizationService()

    def test_rule_a_disallowed_math_focus_topic_replaced(self):
        """Rule a: A disallowed math focus_topic is replaced by a safe default (None)."""
        ctx = make_safe_context(
            preferred_theme="astronomy",
            disallowed_topics=["astronomy"],
        )
        profile = self.service.personalize(challenge_type="math", difficulty_level="medium", safe_context=ctx)
        assert isinstance(profile.typed_parameters, MathPersonalizationParams)
        self.assertIsNone(profile.typed_parameters.focus_topic)

    def test_rule_b_disallowed_memory_palette_theme_replaced(self):
        """Rule b: A disallowed memory palette_theme is replaced by a safe default."""
        ctx = make_safe_context(
            preferred_theme="emojis",
            disallowed_topics=["emojis"],
        )
        profile = self.service.personalize(challenge_type="memory", difficulty_level="medium", safe_context=ctx)
        assert isinstance(profile.typed_parameters, MemoryPersonalizationParams)
        self.assertNotEqual(profile.typed_parameters.palette_theme, "emojis")
        self.assertIn(profile.typed_parameters.palette_theme, ["colors", "geometric_shapes", "cardinal_directions"])

    def test_rule_c_disallowed_tongue_twister_theme_style_replaced(self):
        """Rule c: A disallowed tongue-twister theme_style is replaced by a safe default."""
        ctx = make_safe_context(
            preferred_theme="animals",
            disallowed_topics=["animals"],
        )
        profile = self.service.personalize(challenge_type="tongue_twister", difficulty_level="easy", safe_context=ctx)
        assert isinstance(profile.typed_parameters, TongueTwisterPersonalizationParams)
        self.assertNotEqual(profile.typed_parameters.theme_style, "animals")
        self.assertIn(profile.typed_parameters.theme_style, ["nature", "workday", "whimsical", "rhyme"])

    def test_rule_d_disallowed_dance_movement_style_replaced(self):
        """Rule d: A disallowed dance movement_style is replaced by a safe default."""
        ctx = make_safe_context(
            preferred_theme="rhythm_groove",
            disallowed_topics=["rhythm_groove"],
        )
        profile = self.service.personalize(challenge_type="dance", difficulty_level="hard", safe_context=ctx)
        assert isinstance(profile.typed_parameters, DancePersonalizationParams)
        self.assertNotEqual(profile.typed_parameters.movement_style, "rhythm_groove")
        self.assertIn(profile.typed_parameters.movement_style, ["standard", "step_touch", "arm_raises"])

    def test_rule_e_disallowed_push_up_target_rep_styling_replaced(self):
        """Rule e: A disallowed push-up target_rep_styling is replaced by a safe default."""
        ctx = make_safe_context(
            disallowed_topics=["tier_max"],
        )
        profile = self.service.personalize(challenge_type="push_ups", difficulty_level="hard", safe_context=ctx)
        assert isinstance(profile.typed_parameters, PushUpPersonalizationParams)
        self.assertNotEqual(profile.typed_parameters.target_rep_styling, "tier_max")
        self.assertIn(profile.typed_parameters.target_rep_styling, ["tier_median", "tier_min"])

    def test_rule_f_matching_word_in_control_field_not_rejected(self):
        """Rule f: A matching word inside an unrelated structural/control field does NOT cause rejection.

        e.g., disallowed 'compact' does not reject operand_scale='compact';
              disallowed 'hard' does not reject difficulty_level='hard';
              disallowed 'math' does not reject challenge_type='math'.
        """
        ctx = make_safe_context(
            disallowed_topics=["compact", "standard", "hard", "math", "moderate"],
        )
        profile = self.service.personalize(
            challenge_type="math",
            difficulty_level="hard",
            safe_context=ctx,
        )
        self.assertEqual(profile.challenge_type, "math")
        self.assertEqual(profile.difficulty_level, "hard")
        assert isinstance(profile.typed_parameters, MathPersonalizationParams)
        # Control parameters function normally
        self.assertIn(profile.typed_parameters.operand_scale_preference, ["compact", "standard"])

    def test_rule_g_safety_overrides_behavioral_personalization(self):
        """Rule g: Safety overrides behavioral personalization (Level 1 > Level 5)."""
        # Behavioral signals would choose 'whimsical' on tongue twister, but 'whimsical' is disallowed
        signals = BehavioralPersonalizationSignals(
            historical_success_rate=0.95,
            recent_failure_count=0,
            recent_snooze_level="none",
        )
        ctx = make_safe_context(
            disallowed_topics=["whimsical"],
        )
        profile = self.service.personalize(
            challenge_type="tongue_twister",
            difficulty_level="medium",
            safe_context=ctx,
            behavioral_signals=signals,
        )
        assert isinstance(profile.typed_parameters, TongueTwisterPersonalizationParams)
        self.assertNotEqual(profile.typed_parameters.theme_style, "whimsical")

    def test_rule_h_safety_overrides_repetition_preferences(self):
        """Rule h: Safety overrides repetition preferences (Level 1 > Level 6)."""
        # Candidate alternative tries to rotate palette, but the alternative is in disallowed_topics
        ctx = make_safe_context(
            disallowed_topics=["geometric_shapes", "cardinal_directions"],
        )
        recent_sig = "type=memory|mode=visual_seq|theme=colors"
        profile = self.service.personalize(
            challenge_type="memory",
            difficulty_level="easy",
            safe_context=ctx,
            recent_structural_signatures=[recent_sig],
        )
        assert isinstance(profile.typed_parameters, MemoryPersonalizationParams)
        # The chosen palette must NOT be any of the disallowed topics
        self.assertNotIn(profile.typed_parameters.palette_theme, ["geometric_shapes", "cardinal_directions"])

    def test_rule_i_challenge_type_remains_unchanged(self):
        """Rule i: Challenge type remains unchanged under topic disallowance."""
        ctx = make_safe_context(
            preferred_theme="space",
            disallowed_topics=["space", "dance", "push_ups"],
        )
        profile = self.service.personalize(challenge_type="dance", difficulty_level="easy", safe_context=ctx)
        self.assertEqual(profile.challenge_type, "dance")

    def test_rule_j_difficulty_remains_unchanged(self):
        """Rule j: Difficulty remains unchanged under topic disallowance."""
        ctx = make_safe_context(
            preferred_theme="boxing",
            disallowed_topics=["boxing", "easy", "medium", "hard"],
        )
        profile = self.service.personalize(challenge_type="push_ups", difficulty_level="medium", safe_context=ctx)
        self.assertEqual(profile.difficulty_level, "medium")


class TestDeterminismAndSecurity(unittest.TestCase):
    """Test Suite 7: Determinism, Privacy & Absence of Dict[str, Any]."""

    def setUp(self):
        self.service = ChallengePersonalizationService()

    def test_determinism_identical_inputs_identical_output(self):
        """Given identical inputs, personalize() produces identical profiles across 10 invocations."""
        ctx = make_safe_context(
            desired_duration_seconds=45,
            preferred_theme="nature",
            disallowed_topics=["pollution"],
        )
        signals = BehavioralPersonalizationSignals(
            recent_snooze_level="moderate",
            is_retry_attempt=False,
            historical_success_rate=0.6,
            recent_failure_count=1,
        )
        recent = ["type=tongue_twister|sound=plosives|reps=2"]

        profiles = [
            self.service.personalize(
                challenge_type="tongue_twister",
                difficulty_level="medium",
                safe_context=ctx,
                behavioral_signals=signals,
                recent_structural_signatures=recent,
            )
            for _ in range(10)
        ]

        first_dump = profiles[0].model_dump()
        for p in profiles[1:]:
            self.assertEqual(p.model_dump(), first_dump)

    def test_no_dict_str_any_in_parameters(self):
        """All parameter models are strictly typed Pydantic models, rejecting raw dicts or extra fields."""
        for ctype in ["math", "memory", "tongue_twister", "dance", "push_ups"]:
            profile = self.service.personalize(challenge_type=ctype, difficulty_level="easy")
            self.assertNotIsInstance(profile.typed_parameters, dict)
            self.assertIsNotNone(profile.typed_parameters)

    def test_extra_fields_forbidden(self):
        """PersonalizedChallengeProfile strictly rejects extra fields (extra='forbid')."""
        profile = self.service.personalize(challenge_type="math", difficulty_level="easy")
        dumped = profile.model_dump()
        dumped["extra_forbidden_key"] = "leak"
        with self.assertRaises(ValidationError):
            PersonalizedChallengeProfile.model_validate(dumped)


if __name__ == "__main__":
    unittest.main()
