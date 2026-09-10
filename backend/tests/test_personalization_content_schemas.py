"""Unit tests for Phase 4.5 Step 1 Personalization Schemas and Data Contracts.

Validates:
- BehavioralPersonalizationSignals (strict types, historical_success_rate None default, bounds, forbid extra)
- MathPersonalizationParams (topic regex, bounds, operations, scale)
- MemoryPersonalizationParams (modes, themes, non-numeric enforcement)
- TongueTwisterPersonalizationParams (sound families, themes)
- DancePersonalizationParams (movement style, pacing)
- PushUpPersonalizationParams (cadence tempo, rep styling)
- PersonalizedChallengeProfile (authority immutability, type-parameter matching,
  signature validation, PII/identity rejection, SafePersonalizationContext integration)
"""
import unittest
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


class TestBehavioralPersonalizationSignals(unittest.TestCase):
    """Test suite for BehavioralPersonalizationSignals schema."""

    def test_default_values(self):
        """Verify defaults: historical_success_rate is None (no-history != 100% success)."""
        signals = BehavioralPersonalizationSignals()
        self.assertEqual(signals.recent_snooze_level, "none")
        self.assertFalse(signals.is_retry_attempt)
        self.assertIsNone(signals.historical_success_rate)
        self.assertEqual(signals.recent_failure_count, 0)

    def test_valid_custom_values(self):
        """Verify explicit initialization with valid values."""
        signals = BehavioralPersonalizationSignals(
            recent_snooze_level="high",
            is_retry_attempt=True,
            historical_success_rate=0.75,
            recent_failure_count=2,
        )
        self.assertEqual(signals.recent_snooze_level, "high")
        self.assertTrue(signals.is_retry_attempt)
        self.assertEqual(signals.historical_success_rate, 0.75)
        self.assertEqual(signals.recent_failure_count, 2)

    def test_historical_success_rate_boundary(self):
        """Verify historical_success_rate bounds [0.0, 1.0]."""
        # Valid boundaries
        s0 = BehavioralPersonalizationSignals(historical_success_rate=0.0)
        self.assertEqual(s0.historical_success_rate, 0.0)
        s1 = BehavioralPersonalizationSignals(historical_success_rate=1.0)
        self.assertEqual(s1.historical_success_rate, 1.0)

        # Invalid boundaries
        with self.assertRaises(ValidationError):
            BehavioralPersonalizationSignals(historical_success_rate=-0.01)

        with self.assertRaises(ValidationError):
            BehavioralPersonalizationSignals(historical_success_rate=1.01)

    def test_recent_failure_count_bounds(self):
        """Verify recent_failure_count bounds [0, 10]."""
        with self.assertRaises(ValidationError):
            BehavioralPersonalizationSignals(recent_failure_count=-1)

        with self.assertRaises(ValidationError):
            BehavioralPersonalizationSignals(recent_failure_count=11)

    def test_recent_snooze_level_literals(self):
        """Verify recent_snooze_level rejects unapproved strings."""
        for valid in ["none", "low", "moderate", "high"]:
            signals = BehavioralPersonalizationSignals(recent_snooze_level=valid)
            self.assertEqual(signals.recent_snooze_level, valid)

        with self.assertRaises(ValidationError):
            BehavioralPersonalizationSignals(recent_snooze_level="extreme")

        with self.assertRaises(ValidationError):
            BehavioralPersonalizationSignals(recent_snooze_level="sleep_inertia_high")

    def test_strict_mode_rejects_coercion(self):
        """Verify strict mode rejects bool coercion into numeric fields."""
        with self.assertRaises(ValidationError):
            BehavioralPersonalizationSignals(recent_failure_count=True)

        with self.assertRaises(ValidationError):
            BehavioralPersonalizationSignals(historical_success_rate=False)

    def test_extra_fields_forbidden(self):
        """Verify extra forbidden fields (e.g. user_id) are rejected."""
        with self.assertRaises(ValidationError):
            BehavioralPersonalizationSignals(user_id="test_user")


class TestTypedPersonalizationParams(unittest.TestCase):
    """Test suite for type-specific personalization parameter models."""

    def test_math_params_valid(self):
        """Verify MathPersonalizationParams instantiation and field validation."""
        params = MathPersonalizationParams(
            focus_topic="astronomy",
            preferred_operation="addition",
            operand_scale_preference="standard",
        )
        self.assertEqual(params.focus_topic, "astronomy")
        self.assertEqual(params.preferred_operation, "addition")
        self.assertEqual(params.operand_scale_preference, "standard")

    def test_math_params_focus_topic_sanitization(self):
        """Verify topic validation rejects control characters, bad regex, or excessive length."""
        # Clean stripped
        p = MathPersonalizationParams(focus_topic="  morning routine  ")
        self.assertEqual(p.focus_topic, "morning routine")

        # Rejects special characters like $
        with self.assertRaises(ValidationError):
            MathPersonalizationParams(focus_topic="hacker$topic")

        # Rejects control characters / newlines
        with self.assertRaises(ValidationError):
            MathPersonalizationParams(focus_topic="test\ntopic")

        # Rejects over 30 chars
        with self.assertRaises(ValidationError):
            MathPersonalizationParams(focus_topic="a" * 31)

    def test_math_params_invalid_operation(self):
        """Verify MathPersonalizationParams rejects unsupported operations."""
        with self.assertRaises(ValidationError):
            MathPersonalizationParams(preferred_operation="modulo")

    def test_memory_params_valid(self):
        """Verify MemoryPersonalizationParams with valid non-numeric fields."""
        params = MemoryPersonalizationParams(
            preferred_mode="visual_sequence",
            palette_theme="colors",
        )
        self.assertEqual(params.preferred_mode, "visual_sequence")
        self.assertEqual(params.palette_theme, "colors")

    def test_memory_params_invalid_mode_or_theme(self):
        """Verify MemoryPersonalizationParams rejects unapproved modes or numeric themes."""
        with self.assertRaises(ValidationError):
            MemoryPersonalizationParams(preferred_mode="number_guessing")

        with self.assertRaises(ValidationError):
            MemoryPersonalizationParams(palette_theme="digits")

    def test_tongue_twister_params_valid(self):
        """Verify TongueTwisterPersonalizationParams with valid fields."""
        params = TongueTwisterPersonalizationParams(
            target_sound_family="sibilants",
            theme_style="nature",
        )
        self.assertEqual(params.target_sound_family, "sibilants")
        self.assertEqual(params.theme_style, "nature")

    def test_tongue_twister_params_invalid(self):
        """Verify TongueTwisterPersonalizationParams rejects unapproved sound families."""
        with self.assertRaises(ValidationError):
            TongueTwisterPersonalizationParams(target_sound_family="clicks")

        with self.assertRaises(ValidationError):
            TongueTwisterPersonalizationParams(theme_style="horror")

    def test_dance_params_valid(self):
        """Verify DancePersonalizationParams procedural parameters."""
        params = DancePersonalizationParams(
            movement_style="rhythm_groove",
            pacing="dynamic",
        )
        self.assertEqual(params.movement_style, "rhythm_groove")
        self.assertEqual(params.pacing, "dynamic")

    def test_dance_params_invalid(self):
        """Verify DancePersonalizationParams rejects unsupported movement style."""
        with self.assertRaises(ValidationError):
            DancePersonalizationParams(movement_style="breakdance")

    def test_push_up_params_valid(self):
        """Verify PushUpPersonalizationParams procedural parameters."""
        params = PushUpPersonalizationParams(
            cadence_tempo="tempo_pause",
            target_rep_styling="tier_max",
        )
        self.assertEqual(params.cadence_tempo, "tempo_pause")
        self.assertEqual(params.target_rep_styling, "tier_max")

    def test_push_up_params_invalid(self):
        """Verify PushUpPersonalizationParams rejects unsupported cadence."""
        with self.assertRaises(ValidationError):
            PushUpPersonalizationParams(cadence_tempo="explosive")

    def test_all_params_forbid_extra(self):
        """Verify all parameter models reject extra fields."""
        with self.assertRaises(ValidationError):
            MathPersonalizationParams(extra_field="val")
        with self.assertRaises(ValidationError):
            MemoryPersonalizationParams(extra_field="val")
        with self.assertRaises(ValidationError):
            TongueTwisterPersonalizationParams(extra_field="val")
        with self.assertRaises(ValidationError):
            DancePersonalizationParams(extra_field="val")
        with self.assertRaises(ValidationError):
            PushUpPersonalizationParams(extra_field="val")


class TestPersonalizedChallengeProfile(unittest.TestCase):
    """Test suite for PersonalizedChallengeProfile application container."""

    def test_valid_profile_creation_with_defaults(self):
        """Verify minimal profile creation with authoritative type and difficulty."""
        profile = PersonalizedChallengeProfile(
            challenge_type="math",
            difficulty_level="medium",
        )
        self.assertEqual(profile.challenge_type, "math")
        self.assertEqual(profile.difficulty_level, "medium")
        self.assertIsInstance(profile.safe_context, SafePersonalizationContext)
        self.assertIsInstance(profile.behavioral_signals, BehavioralPersonalizationSignals)
        self.assertEqual(profile.recent_structural_signatures, [])
        self.assertIsNone(profile.typed_parameters)

    def test_valid_profiles_all_challenge_types(self):
        """Verify profile creation across all five canonical types with matching params."""
        profiles = [
            PersonalizedChallengeProfile(
                challenge_type="math",
                difficulty_level="easy",
                typed_parameters=MathPersonalizationParams(focus_topic="finance"),
            ),
            PersonalizedChallengeProfile(
                challenge_type="memory",
                difficulty_level="medium",
                typed_parameters=MemoryPersonalizationParams(preferred_mode="visual_sequence"),
            ),
            PersonalizedChallengeProfile(
                challenge_type="tongue_twister",
                difficulty_level="hard",
                typed_parameters=TongueTwisterPersonalizationParams(target_sound_family="sibilants"),
            ),
            PersonalizedChallengeProfile(
                challenge_type="dance",
                difficulty_level="easy",
                typed_parameters=DancePersonalizationParams(movement_style="step_touch"),
            ),
            PersonalizedChallengeProfile(
                challenge_type="push_ups",
                difficulty_level="medium",
                typed_parameters=PushUpPersonalizationParams(cadence_tempo="steady"),
            ),
        ]
        self.assertEqual(len(profiles), 5)

    def test_dict_based_typed_parameters_resolution(self):
        """Verify dict-based typed_parameters are resolved to the correct typed model."""
        profile = PersonalizedChallengeProfile(
            challenge_type="math",
            difficulty_level="medium",
            typed_parameters={"focus_topic": "astronomy"},
        )
        self.assertIsInstance(profile.typed_parameters, MathPersonalizationParams)
        self.assertEqual(profile.typed_parameters.focus_topic, "astronomy")

    def test_type_parameter_mismatch_rejection(self):
        """Verify model validator rejects parameters not matching challenge_type."""
        with self.assertRaises(ValidationError) as ctx:
            PersonalizedChallengeProfile(
                challenge_type="math",
                difficulty_level="easy",
                typed_parameters=DancePersonalizationParams(movement_style="step_touch"),
            )
        self.assertIn("must be of type MathPersonalizationParams", str(ctx.exception))

        with self.assertRaises(ValidationError) as ctx2:
            PersonalizedChallengeProfile(
                challenge_type="memory",
                difficulty_level="hard",
                typed_parameters=PushUpPersonalizationParams(cadence_tempo="steady"),
            )
        self.assertIn("must be of type MemoryPersonalizationParams", str(ctx2.exception))

    def test_invalid_canonical_type_or_difficulty(self):
        """Verify profile rejects non-canonical challenge type or non-canonical difficulty."""
        with self.assertRaises(ValidationError):
            PersonalizedChallengeProfile(
                challenge_type="number_guessing",
                difficulty_level="easy",
            )

        with self.assertRaises(ValidationError):
            PersonalizedChallengeProfile(
                challenge_type="math",
                difficulty_level="extreme",
            )

    def test_structural_signatures_validation(self):
        """Verify recent_structural_signatures constraints."""
        valid_sigs = ["math:op_addition:2dig", "math:op_multiplication:mixed"]
        p = PersonalizedChallengeProfile(
            challenge_type="math",
            difficulty_level="easy",
            recent_structural_signatures=valid_sigs,
        )
        self.assertEqual(p.recent_structural_signatures, valid_sigs)

        # Max 5 signatures allowed
        with self.assertRaises(ValidationError):
            PersonalizedChallengeProfile(
                challenge_type="math",
                difficulty_level="easy",
                recent_structural_signatures=[f"sig_{i}" for i in range(6)],
            )

        # Empty signature rejected
        with self.assertRaises(ValidationError):
            PersonalizedChallengeProfile(
                challenge_type="math",
                difficulty_level="easy",
                recent_structural_signatures=[""],
            )

        # Signature with newlines rejected
        with self.assertRaises(ValidationError):
            PersonalizedChallengeProfile(
                challenge_type="math",
                difficulty_level="easy",
                recent_structural_signatures=["sig\ninvalid"],
            )

        # Signature with forbidden identity keys rejected
        with self.assertRaises(ValidationError) as ctx:
            PersonalizedChallengeProfile(
                challenge_type="math",
                difficulty_level="easy",
                recent_structural_signatures=["sig:user_id=12345"],
            )
        self.assertIn("forbidden identity key", str(ctx.exception))

    def test_pii_and_identity_fields_forbidden(self):
        """Verify profile forbids database IDs, PII, credentials, or arbitrary dicts."""
        # user_id
        with self.assertRaises(ValidationError):
            PersonalizedChallengeProfile(
                challenge_type="math",
                difficulty_level="easy",
                user_id="user_123",
            )

        # alarm_id
        with self.assertRaises(ValidationError):
            PersonalizedChallengeProfile(
                challenge_type="math",
                difficulty_level="easy",
                alarm_id="alarm_456",
            )

        # wake_session_id
        with self.assertRaises(ValidationError):
            PersonalizedChallengeProfile(
                challenge_type="math",
                difficulty_level="easy",
                wake_session_id="session_789",
            )

        # email
        with self.assertRaises(ValidationError):
            PersonalizedChallengeProfile(
                challenge_type="math",
                difficulty_level="easy",
                email="test@smartwake.ai",
            )

        # arbitrary dict parameters rejected
        with self.assertRaises(ValidationError):
            PersonalizedChallengeProfile(
                challenge_type="math",
                difficulty_level="easy",
                challenge_params={"arbitrary": "value"},
            )

    def test_safe_context_integration(self):
        """Verify SafePersonalizationContext from Phase 4.1 is integrated cleanly."""
        safe_ctx = SafePersonalizationContext(
            desired_duration_seconds=45,
            current_session_snooze_count=2,
            preferred_theme="space exploration",
        )
        profile = PersonalizedChallengeProfile(
            challenge_type="math",
            difficulty_level="hard",
            safe_context=safe_ctx,
        )
        self.assertEqual(profile.safe_context.desired_duration_seconds, 45)
        self.assertEqual(profile.safe_context.current_session_snooze_count, 2)
        self.assertEqual(profile.safe_context.preferred_theme, "space exploration")


if __name__ == "__main__":
    unittest.main()
