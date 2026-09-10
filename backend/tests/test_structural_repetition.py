"""Unit tests for Phase 4.5 Step 2: Structural Repetition Avoidance.

Covers:
A. Signature determinism (identical inputs & equivalent normalized representations)
B. Challenge-type coverage (math, memory, tongue_twister, dance, push_ups)
C. Structural distinction (different structures yield distinct signatures)
D. Repeat detection (empty, present, absent, duplicate histories)
E. Recent window (max capacity 5, LRU duplicate promotion [A]->[B,A]->[C,B,A]->add B->[B,C,A], eviction)
F. Bounds (signatures <= 60 characters, empty/oversized rejected)
G. Security (PII/identity keys rejected, no control chars/newlines, unsupported types rejected)
H. T0 conceptual boundary (zero database dependencies, caller-supplied history only)
I. Integration with PersonalizedChallengeProfile
"""
import unittest
from typing import List, Optional

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
from backend.app.services.genai.structural_repetition import (
    MAX_SIGNATURE_LENGTH,
    MAX_WINDOW_CAPACITY,
    DanceStructuralInput,
    InvalidSignatureFormatError,
    InvalidStructuralInputError,
    MathStructuralInput,
    MemoryStructuralInput,
    PushUpStructuralInput,
    StructuralSignatureWindow,
    TongueTwisterStructuralInput,
    RecentSignatureWindow,
    bucket_dance_steps,
    bucket_duration,
    bucket_operand_scale_from_values,
    bucket_push_up_reps,
    bucket_repetition,
    bucket_repetition_count,
    bucket_sequence_length,
    bucket_word_count,
    build_dance_signature,
    build_math_signature,
    build_memory_signature,
    build_push_up_signature,
    build_push_ups_signature,
    build_signature_from_profile,
    build_tongue_twister_signature,
    canonicalize_cadence_token,
    canonicalize_dance_style_token,
    canonicalize_operation_name,
    canonicalize_palette_theme_token,
    canonicalize_recall_mode_token,
    canonicalize_repetition_token,
    canonicalize_sound_family_token,
    canonicalize_text,
    generate_structural_signature,
    has_structural_repeat,
    is_structural_repeat,
    normalize_cadence,
    normalize_memory_mode,
    normalize_movement_style,
    normalize_operation,
    normalize_pace,
    normalize_scale,
    normalize_sound_family,
    update_recent_signatures,
    validate_signature,
    validate_structural_signature,
)


class TestStructuralRepetitionDeterminism(unittest.TestCase):
    """Test group A: Signature Determinism."""

    def test_math_signature_determinism(self):
        inp1 = MathStructuralInput(operation="addition", operand_scale="compact", expression_type="binary")
        inp2 = MathStructuralInput(operation="addition", operand_scale="compact", expression_type="binary")
        sig1 = build_math_signature(inp1)
        sig2 = build_math_signature(inp2)
        self.assertEqual(sig1, sig2)
        self.assertEqual(sig1, "type=math|op=addition|scale=compact")

    def test_canonicalization_equivalence(self):
        """Equivalent raw representations canonicalize to the exact same signature."""
        self.assertEqual(canonicalize_operation_name("+"), "addition")
        self.assertEqual(canonicalize_operation_name("add"), "addition")
        self.assertEqual(canonicalize_operation_name("ADDITION "), "addition")
        self.assertEqual(canonicalize_operation_name("*"), "multiplication")
        self.assertEqual(canonicalize_operation_name("mult"), "multiplication")
        self.assertEqual(canonicalize_operation_name("x"), "multiplication")

        self.assertEqual(canonicalize_recall_mode_token("visual_sequence"), "visual_seq")
        self.assertEqual(canonicalize_recall_mode_token("visual_seq"), "visual_seq")
        self.assertEqual(canonicalize_recall_mode_token("spatial_pattern_recall"), "spatial_pat")
        self.assertEqual(canonicalize_recall_mode_token("dynamic_spatial_path"), "dynamic_path")
        self.assertEqual(canonicalize_recall_mode_token("symbol_chronological_order"), "symbol_order")

        self.assertEqual(canonicalize_palette_theme_token("geometric_shapes"), "shapes")
        self.assertEqual(canonicalize_palette_theme_token("cardinal_directions"), "directions")

        self.assertEqual(canonicalize_repetition_token("2_rep"), "2")
        self.assertEqual(canonicalize_repetition_token("3_plus"), "3+")

    def test_memory_signature_determinism(self):
        inp1 = MemoryStructuralInput(recall_mode="visual_sequence", sequence_length_bucket="medium", palette_theme="colors")
        inp2 = MemoryStructuralInput(recall_mode="visual_sequence", sequence_length_bucket="medium", palette_theme="colors")
        sig1 = build_memory_signature(inp1)
        sig2 = build_memory_signature(inp2)
        self.assertEqual(sig1, sig2)
        self.assertEqual(sig1, "type=memory|mode=visual_seq|len=medium|theme=colors")


class TestChallengeTypeCoverage(unittest.TestCase):
    """Test group B: All 5 canonical challenge types supported."""

    def test_math_signature_generation(self):
        inp = MathStructuralInput(operation="multiplication", operand_scale="standard", difficulty="hard")
        sig = generate_structural_signature("math", inp)
        self.assertTrue(sig.startswith("type=math|"))
        self.assertIn("op=multiplication", sig)
        self.assertIn("diff=hard", sig)
        self.assertLessEqual(len(sig), MAX_SIGNATURE_LENGTH)

    def test_memory_signature_generation(self):
        inp = MemoryStructuralInput(recall_mode="spatial_pattern_recall", matrix_size="4x4", sequence_length_bucket="short")
        sig = generate_structural_signature("memory", inp)
        self.assertTrue(sig.startswith("type=memory|"))
        self.assertIn("mode=spatial_pat", sig)
        self.assertIn("grid=4x4", sig)
        self.assertLessEqual(len(sig), MAX_SIGNATURE_LENGTH)

    def test_tongue_twister_signature_generation(self):
        inp = TongueTwisterStructuralInput(
            target_sound_family="sibilants",
            repetition_bucket="2_rep",
            word_count_bucket="medium",
            theme_style="animals",
        )
        sig = generate_structural_signature("tongue_twister", inp)
        self.assertTrue(sig.startswith("type=tongue_twister|"))
        self.assertIn("sound=sibilants", sig)
        self.assertIn("reps=2", sig)
        self.assertIn("len=medium", sig)
        self.assertLessEqual(len(sig), MAX_SIGNATURE_LENGTH)

    def test_dance_signature_generation(self):
        inp = DanceStructuralInput(
            movement_style="rhythm_groove",
            pacing="dynamic",
            routine_length_bucket="medium",
        )
        sig = generate_structural_signature("dance", inp)
        self.assertTrue(sig.startswith("type=dance|"))
        self.assertIn("style=rhythm_groove", sig)
        self.assertIn("pace=dynamic", sig)
        self.assertLessEqual(len(sig), MAX_SIGNATURE_LENGTH)

    def test_push_ups_signature_generation(self):
        inp = PushUpStructuralInput(
            cadence_style="tempo_pause",
            repetition_bucket="tier_median",
            rom_requirement="strict",
        )
        sig = generate_structural_signature("push_ups", inp)
        self.assertTrue(sig.startswith("type=push_ups|"))
        self.assertIn("cad=tempo_pause", sig)
        self.assertIn("reps=tier_median", sig)
        self.assertIn("rom=strict", sig)
        self.assertLessEqual(len(sig), MAX_SIGNATURE_LENGTH)


class TestStructuralDistinction(unittest.TestCase):
    """Test group C: Meaningfully different structures yield different signatures."""

    def test_math_structural_distinction(self):
        sig_add = build_math_signature(MathStructuralInput(operation="addition", operand_scale="compact"))
        sig_mult = build_math_signature(MathStructuralInput(operation="multiplication", operand_scale="compact"))
        sig_large = build_math_signature(MathStructuralInput(operation="addition", operand_scale="large"))
        self.assertNotEqual(sig_add, sig_mult)
        self.assertNotEqual(sig_add, sig_large)

    def test_memory_structural_distinction(self):
        sig_vis = build_memory_signature(MemoryStructuralInput(recall_mode="visual_sequence", palette_theme="colors"))
        sig_spat = build_memory_signature(MemoryStructuralInput(recall_mode="spatial_pattern_recall", matrix_size="3x3"))
        sig_path = build_memory_signature(MemoryStructuralInput(recall_mode="dynamic_spatial_path", matrix_size="4x4"))
        self.assertNotEqual(sig_vis, sig_spat)
        self.assertNotEqual(sig_spat, sig_path)

    def test_tongue_twister_structural_distinction(self):
        sig_sib = build_tongue_twister_signature(TongueTwisterStructuralInput(target_sound_family="sibilants", repetition_bucket="1_rep"))
        sig_plo = build_tongue_twister_signature(TongueTwisterStructuralInput(target_sound_family="plosives", repetition_bucket="3_plus"))
        self.assertNotEqual(sig_sib, sig_plo)

    def test_dance_structural_distinction(self):
        sig_groove = build_dance_signature(DanceStructuralInput(movement_style="rhythm_groove", pacing="dynamic"))
        sig_arms = build_dance_signature(DanceStructuralInput(movement_style="arm_raises", pacing="slow"))
        self.assertNotEqual(sig_groove, sig_arms)

    def test_push_ups_structural_distinction(self):
        sig_pause = build_push_ups_signature(PushUpStructuralInput(cadence_style="tempo_pause", repetition_bucket="high"))
        sig_steady = build_push_ups_signature(PushUpStructuralInput(cadence_style="steady", repetition_bucket="low"))
        self.assertNotEqual(sig_pause, sig_steady)


class TestRepeatDetection(unittest.TestCase):
    """Test group D: Repeat Detection."""

    def test_empty_or_none_history(self):
        sig = "type=math|op=multiplication|scale=compact"
        self.assertFalse(is_structural_repeat(sig, None))
        self.assertFalse(is_structural_repeat(sig, []))

    def test_exact_signature_in_history(self):
        sig = "type=math|op=multiplication|scale=compact"
        history = [
            "type=math|op=addition|scale=standard",
            "type=math|op=multiplication|scale=compact",
            "type=memory|mode=visual_seq|theme=colors",
        ]
        self.assertTrue(is_structural_repeat(sig, history))

    def test_absent_signature(self):
        sig = "type=push_ups|cad=steady|reps=low"
        history = [
            "type=math|op=addition|scale=standard",
            "type=memory|mode=visual_seq|theme=colors",
        ]
        self.assertFalse(is_structural_repeat(sig, history))

    def test_duplicate_history_safely_handled(self):
        sig = "type=dance|style=rhythm_groove|pace=dynamic"
        history = [
            "type=dance|style=rhythm_groove|pace=dynamic",
            "type=dance|style=rhythm_groove|pace=dynamic",
        ]
        self.assertTrue(is_structural_repeat(sig, history))

    def test_malformed_entry_in_history_safely_ignored(self):
        sig = "type=math|op=addition|scale=standard"
        history: List[Optional[str]] = [
            "invalid_non_type_signature",
            None,  # non-string
            "type=math|op=addition|scale=standard",
        ]
        self.assertTrue(is_structural_repeat(sig, history))


class TestRecentSignatureWindow(unittest.TestCase):
    """Test group E: Bounded LRU-style Recent-Signature Window."""

    def test_lru_promotion_behavior(self):
        """Verify: A -> [A], B -> [B, A], C -> [C, B, A], B again -> [B, C, A]."""
        window = StructuralSignatureWindow(max_capacity=5)

        sig_a = "type=math|op=addition|scale=standard"
        sig_b = "type=memory|mode=visual_seq|theme=colors"
        sig_c = "type=tongue_twister|sound=sibilants|reps=2"

        window.add_signature(sig_a)
        self.assertEqual(window.get_signatures(), [sig_a])

        window.add_signature(sig_b)
        self.assertEqual(window.get_signatures(), [sig_b, sig_a])

        window.add_signature(sig_c)
        self.assertEqual(window.get_signatures(), [sig_c, sig_b, sig_a])

        # Add B again -> B must be promoted to front: [B, C, A]
        window.add_signature(sig_b)
        self.assertEqual(window.get_signatures(), [sig_b, sig_c, sig_a])

    def test_capacity_bound_and_eviction(self):
        """Verify max capacity K=5 strictly enforced with tail eviction."""
        window = StructuralSignatureWindow(max_capacity=5)
        sigs = [
            f"type=math|op=addition|scale=compact|step={i}"
            for i in range(1, 7)
        ]
        for s in sigs:
            window.add_signature(s)

        self.assertEqual(len(window), 5)
        self.assertEqual(len(window.get_signatures()), 5)
        # Oldest sigs[0] should have been evicted
        self.assertFalse(window.has_signature(sigs[0]))
        # Newest sigs[-1] is at index 0
        self.assertEqual(window.get_signatures()[0], sigs[-1])

    def test_has_signature_method(self):
        window = StructuralSignatureWindow()
        sig = "type=push_ups|cad=steady|reps=tier_median"
        self.assertFalse(window.has_signature(sig))
        window.add_signature(sig)
        self.assertTrue(window.has_signature(sig))

    def test_functional_update_recent_signatures(self):
        """Verify pure functional update_recent_signatures helper."""
        initial = ["type=math|op=addition|scale=compact"]
        new_sig = "type=memory|mode=visual_seq|theme=colors"
        res = update_recent_signatures(initial, new_sig, max_capacity=5)
        self.assertEqual(res, [new_sig, initial[0]])

        # Promoting duplicate with functional update
        res2 = update_recent_signatures(res, initial[0], max_capacity=5)
        self.assertEqual(res2, [initial[0], new_sig])


class TestBoundsAndValidation(unittest.TestCase):
    """Test group F: Length, Bounds, and Formatting."""

    def test_signature_length_bound_60_chars(self):
        """Ensure all valid signatures are <= 60 chars."""
        # Longest possible combinations
        s1 = build_tongue_twister_signature(
            TongueTwisterStructuralInput(
                target_sound_family="sibilants",
                repetition_bucket="3_plus",
                word_count_bucket="medium",
                theme_style="whimsical",
            )
        )
        self.assertLessEqual(len(s1), 60)

        s2 = build_dance_signature(
            DanceStructuralInput(
                movement_style="rhythm_groove",
                pacing="dynamic",
                routine_length_bucket="medium",
            )
        )
        self.assertLessEqual(len(s2), 60)

        s3 = build_push_ups_signature(
            PushUpStructuralInput(
                cadence_style="tempo_pause",
                repetition_bucket="tier_median",
                rom_requirement="strict",
            )
        )
        self.assertLessEqual(len(s3), 60)

        s4 = build_memory_signature(
            MemoryStructuralInput(
                recall_mode="symbol_chronological_order",
                sequence_length_bucket="long",
                palette_theme="geometric_shapes",
            )
        )
        self.assertLessEqual(len(s4), 60)

    def test_empty_signature_rejected(self):
        with self.assertRaises(InvalidSignatureFormatError):
            validate_structural_signature("")

        with self.assertRaises(InvalidSignatureFormatError):
            validate_structural_signature("   ")

    def test_oversized_signature_rejected(self):
        oversized = "type=math|" + ("x" * 55)
        self.assertGreater(len(oversized), 60)
        with self.assertRaises(InvalidSignatureFormatError):
            validate_structural_signature(oversized)

    def test_non_string_signature_rejected(self):
        with self.assertRaises(InvalidSignatureFormatError):
            validate_structural_signature(12345)  # type: ignore


class TestSecurityAndPIIRejection(unittest.TestCase):
    """Test group G: Security, PII, Control Characters, Unsupported Types."""

    def test_forbidden_identity_keys_rejected(self):
        forbidden_keys = ["user_id", "email", "alarm_id", "session_id", "password"]
        for key in forbidden_keys:
            bad_sig = f"type=math|op=addition|{key}=123"
            with self.assertRaises(InvalidSignatureFormatError):
                validate_structural_signature(bad_sig)

    def test_control_characters_and_newlines_rejected(self):
        with self.assertRaises(InvalidSignatureFormatError):
            validate_structural_signature("type=math|op=addition\n|scale=compact")

        with self.assertRaises(InvalidSignatureFormatError):
            validate_structural_signature("type=math|op=addition\r|scale=compact")

        with self.assertRaises(InvalidSignatureFormatError):
            validate_structural_signature("type=math|op=addition\x00|scale=compact")

    def test_unsupported_challenge_type_rejected(self):
        with self.assertRaises(InvalidSignatureFormatError):
            validate_structural_signature("type=trivia|difficulty=easy")

        with self.assertRaises(InvalidStructuralInputError):
            generate_structural_signature("unsupported_type", MathStructuralInput(operation="addition"))  # type: ignore

    def test_mismatched_structural_input_model_rejected(self):
        with self.assertRaises(InvalidStructuralInputError):
            generate_structural_signature("math", MemoryStructuralInput(recall_mode="visual_sequence"))  # type: ignore


class TestT0ConceptualBoundary(unittest.TestCase):
    """Test group H: T0 Boundary (Pure in-memory, no DB, caller-supplied history only)."""

    def test_pure_in_memory_execution(self):
        """Structural repetition service functions require zero database session or connection."""
        sig = build_math_signature(MathStructuralInput(operation="addition"))
        history = ["type=math|op=subtraction|scale=standard"]
        result = is_structural_repeat(sig, history)
        self.assertFalse(result)

    def test_no_current_outcome_fields_in_models(self):
        """Ensure input models forbid completion, success, score, or verification outcome fields."""
        with self.assertRaises(Exception):
            MathStructuralInput(operation="addition", is_completed=True)  # type: ignore

        with self.assertRaises(Exception):
            MemoryStructuralInput(recall_mode="visual_sequence", score=100)  # type: ignore


class TestIntegrationWithProfile(unittest.TestCase):
    """Test group I: Integration with Phase 4.5 Step 1 PersonalizedChallengeProfile."""

    def test_build_signature_from_math_profile(self):
        profile = PersonalizedChallengeProfile(
            challenge_type="math",
            difficulty_level="medium",
            typed_parameters=MathPersonalizationParams(
                preferred_operation="multiplication",
                operand_scale_preference="compact",
            ),
        )
        sig = build_signature_from_profile(profile)
        self.assertEqual(sig, "type=math|op=multiplication|scale=compact|diff=medium")

    def test_build_signature_from_memory_profile(self):
        profile = PersonalizedChallengeProfile(
            challenge_type="memory",
            difficulty_level="easy",
            typed_parameters=MemoryPersonalizationParams(
                preferred_mode="spatial_pattern_recall",
                palette_theme="colors",
            ),
        )
        sig = build_signature_from_profile(profile)
        self.assertEqual(sig, "type=memory|mode=spatial_pat|theme=colors")

    def test_build_signature_from_tongue_twister_profile(self):
        profile = PersonalizedChallengeProfile(
            challenge_type="tongue_twister",
            difficulty_level="hard",
            typed_parameters=TongueTwisterPersonalizationParams(
                target_sound_family="plosives",
                theme_style="nature",
            ),
        )
        sig = build_signature_from_profile(profile)
        self.assertEqual(sig, "type=tongue_twister|sound=plosives|reps=2|theme=nature")

    def test_build_signature_from_dance_profile(self):
        profile = PersonalizedChallengeProfile(
            challenge_type="dance",
            difficulty_level="medium",
            typed_parameters=DancePersonalizationParams(
                movement_style="step_touch",
                pacing="slow",
            ),
        )
        sig = build_signature_from_profile(profile)
        self.assertEqual(sig, "type=dance|style=step_touch|pace=slow")

    def test_build_signature_from_push_ups_profile(self):
        profile = PersonalizedChallengeProfile(
            challenge_type="push_ups",
            difficulty_level="easy",
            typed_parameters=PushUpPersonalizationParams(
                cadence_tempo="steady",
                target_rep_styling="tier_min",
            ),
        )
        sig = build_signature_from_profile(profile)
        self.assertEqual(sig, "type=push_ups|cad=steady|reps=tier_min")

    def test_generated_signatures_pass_profile_validation(self):
        """Verify signatures generated by the service cleanly validate inside PersonalizedChallengeProfile."""
        sig1 = build_math_signature(MathStructuralInput(operation="addition", operand_scale="compact"))
        sig2 = build_memory_signature(MemoryStructuralInput(recall_mode="visual_sequence", palette_theme="emojis"))
        sig3 = build_tongue_twister_signature(TongueTwisterStructuralInput(target_sound_family="liquids"))
        sig4 = build_dance_signature(DanceStructuralInput(movement_style="arm_raises", pacing="dynamic"))
        sig5 = build_push_ups_signature(PushUpStructuralInput(cadence_style="tempo_pause", repetition_bucket="tier_median"))

        profile = PersonalizedChallengeProfile(
            challenge_type="math",
            difficulty_level="medium",
            recent_structural_signatures=[sig1, sig2, sig3, sig4, sig5],
        )
        self.assertEqual(len(profile.recent_structural_signatures), 5)


class TestBucketingHelpers(unittest.TestCase):
    """Test bucketing utility functions."""

    def test_sequence_length_buckets(self):
        self.assertEqual(bucket_sequence_length(2), "short")
        self.assertEqual(bucket_sequence_length(4), "short")
        self.assertEqual(bucket_sequence_length(5), "medium")
        self.assertEqual(bucket_sequence_length(7), "medium")
        self.assertEqual(bucket_sequence_length(8), "long")
        self.assertEqual(bucket_sequence_length(12), "long")

    def test_word_count_buckets(self):
        self.assertEqual(bucket_word_count(6), "short")
        self.assertEqual(bucket_word_count(8), "short")
        self.assertEqual(bucket_word_count(12), "medium")
        self.assertEqual(bucket_word_count(16), "medium")
        self.assertEqual(bucket_word_count(20), "long")

    def test_repetition_count_buckets(self):
        self.assertEqual(bucket_repetition_count(1), "1")
        self.assertEqual(bucket_repetition_count(2), "2")
        self.assertEqual(bucket_repetition_count(3), "3+")
        self.assertEqual(bucket_repetition_count(5), "3+")

    def test_push_up_reps_buckets(self):
        self.assertEqual(bucket_push_up_reps(5), "low")
        self.assertEqual(bucket_push_up_reps(8), "medium")
        self.assertEqual(bucket_push_up_reps(15), "high")

    def test_dance_steps_buckets(self):
        self.assertEqual(bucket_dance_steps(3), "short")
        self.assertEqual(bucket_dance_steps(6), "medium")
        self.assertEqual(bucket_dance_steps(10), "long")

    def test_operand_scale_from_values(self):
        self.assertEqual(bucket_operand_scale_from_values([3, 7]), "compact")
        self.assertEqual(bucket_operand_scale_from_values([12, 5]), "compact")
        self.assertEqual(bucket_operand_scale_from_values([15, 8]), "standard")
        self.assertEqual(bucket_operand_scale_from_values([99, 42]), "standard")
        self.assertEqual(bucket_operand_scale_from_values([105, 12]), "large")


class TestUserRequirement2Aliases(unittest.TestCase):
    """Verify all explicit functions and aliases named in Step 2 requirements."""

    def test_canonicalize_text(self):
        self.assertEqual(canonicalize_text("  Hello   World  "), "hello world")
        with self.assertRaises(InvalidStructuralInputError):
            canonicalize_text("   ")
        with self.assertRaises(InvalidStructuralInputError):
            canonicalize_text("user_id=123")
        with self.assertRaises(InvalidStructuralInputError):
            canonicalize_text("bad\x00control")
        with self.assertRaises(InvalidStructuralInputError):
            canonicalize_text("bad\nnewline")
        with self.assertRaises(InvalidStructuralInputError):
            canonicalize_text("bad\rcarriage_return")
        with self.assertRaises(InvalidStructuralInputError):
            canonicalize_text("bad\ttab")

    def test_bucket_duration(self):
        self.assertEqual(bucket_duration(15), "short")
        self.assertEqual(bucket_duration(20), "short")
        self.assertEqual(bucket_duration(30), "medium")
        self.assertEqual(bucket_duration(45), "medium")
        self.assertEqual(bucket_duration(60), "long")

    def test_bucket_repetition_alias(self):
        self.assertEqual(bucket_repetition(1), "1")
        self.assertEqual(bucket_repetition(2), "2")
        self.assertEqual(bucket_repetition(4), "3+")

    def test_normalizers(self):
        self.assertEqual(normalize_operation("mult"), "multiplication")
        self.assertEqual(normalize_scale("compact"), "compact")
        self.assertEqual(normalize_scale("small"), "compact")
        self.assertEqual(normalize_scale("big"), "large")
        self.assertEqual(normalize_memory_mode("dynamic_spatial_path"), "dynamic_path")
        self.assertEqual(normalize_sound_family("plosives"), "plosives")
        self.assertEqual(normalize_movement_style("step_touch"), "step_touch")
        self.assertEqual(normalize_pace("dynamic"), "dynamic")
        self.assertEqual(normalize_cadence("steady"), "steady")

    def test_validate_signature_alias(self):
        sig = "type=math|op=addition|scale=compact"
        self.assertEqual(validate_signature(sig), sig)

    def test_has_structural_repeat_alias(self):
        sig = "type=math|op=addition|scale=compact"
        history = ["type=math|op=addition|scale=compact"]
        self.assertTrue(has_structural_repeat(sig, history))
        self.assertFalse(has_structural_repeat(sig, []))

    def test_build_push_up_signature_alias(self):
        inp = PushUpStructuralInput(cadence_style="steady", repetition_bucket="low")
        self.assertEqual(build_push_up_signature(inp), build_push_ups_signature(inp))

    def test_recent_signature_window_alias(self):
        win = RecentSignatureWindow(max_capacity=5)
        sig = "type=dance|style=standard|pace=moderate"
        win.add_signature(sig)
        self.assertTrue(win.has_signature(sig))
        self.assertEqual(win.get_signatures(), [sig])


class TestCanonicalizeTextSecurity(unittest.TestCase):
    """Explicit verification for canonicalize_text() security order & control characters."""

    def test_rejects_non_string(self):
        with self.assertRaises(InvalidStructuralInputError):
            canonicalize_text(123)  # type: ignore
        with self.assertRaises(InvalidStructuralInputError):
            canonicalize_text(None)  # type: ignore

    def test_rejects_newline(self):
        with self.assertRaises(InvalidStructuralInputError):
            canonicalize_text("hello\nworld")
        with self.assertRaises(InvalidStructuralInputError):
            canonicalize_text("\nhello")
        with self.assertRaises(InvalidStructuralInputError):
            canonicalize_text("trailing\n")

    def test_rejects_carriage_return(self):
        with self.assertRaises(InvalidStructuralInputError):
            canonicalize_text("hello\rworld")
        with self.assertRaises(InvalidStructuralInputError):
            canonicalize_text("\rhello")
        with self.assertRaises(InvalidStructuralInputError):
            canonicalize_text("trailing\r")
        with self.assertRaises(InvalidStructuralInputError):
            canonicalize_text("hello\r\nworld")

    def test_rejects_tab(self):
        with self.assertRaises(InvalidStructuralInputError):
            canonicalize_text("hello\tworld")
        with self.assertRaises(InvalidStructuralInputError):
            canonicalize_text("\thello")
        with self.assertRaises(InvalidStructuralInputError):
            canonicalize_text("trailing\t")

    def test_rejects_other_control_characters(self):
        with self.assertRaises(InvalidStructuralInputError):
            canonicalize_text("hello\x00world")
        with self.assertRaises(InvalidStructuralInputError):
            canonicalize_text("hello\x1fworld")
        with self.assertRaises(InvalidStructuralInputError):
            canonicalize_text("hello\x07world")  # BEL
        with self.assertRaises(InvalidStructuralInputError):
            canonicalize_text("hello\x08world")  # BS
        with self.assertRaises(InvalidStructuralInputError):
            canonicalize_text("hello\x1bworld")  # ESC

    def test_normal_spaces_normalized_correctly(self):
        self.assertEqual(canonicalize_text("  Hello   World  "), "hello world")
        self.assertEqual(
            canonicalize_text("Multiple   Spaces   Between   Words"),
            "multiple spaces between words",
        )
        self.assertEqual(canonicalize_text("single"), "single")

    def test_forbidden_keys_rejected(self):
        with self.assertRaises(InvalidStructuralInputError):
            canonicalize_text("user_id=123")
        with self.assertRaises(InvalidStructuralInputError):
            canonicalize_text("password reset")

    def test_empty_or_whitespace_only_rejected(self):
        with self.assertRaises(InvalidStructuralInputError):
            canonicalize_text("")
        with self.assertRaises(InvalidStructuralInputError):
            canonicalize_text("     ")


class TestMemorySignatureLengthGuarantee(unittest.TestCase):
    """Explicit verification of memory signature <= 60 chars guarantee."""

    def test_all_valid_memory_combinations_produce_valid_signatures_under_60(self):
        """Exhaustive check across all valid memory parameter combinations (480 combos)."""
        modes = [
            "visual_sequence",
            "spatial_pattern_recall",
            "dynamic_spatial_path",
            "symbol_chronological_order",
        ]
        grids = [None, "2x2", "3x3", "4x4", "5x5", "6x6"]
        lens = [None, "short", "medium", "long"]
        themes = [None, "colors", "geometric_shapes", "cardinal_directions", "emojis"]

        count = 0
        for m in modes:
            for g in grids:
                for l in lens:
                    for t in themes:
                        count += 1
                        inp = MemoryStructuralInput(
                            recall_mode=m,  # type: ignore
                            matrix_size=g,  # type: ignore
                            sequence_length_bucket=l,  # type: ignore
                            palette_theme=t,  # type: ignore
                        )
                        sig = build_memory_signature(inp)
                        self.assertLessEqual(
                            len(sig),
                            MAX_SIGNATURE_LENGTH,
                            f"Signature '{sig}' exceeded {MAX_SIGNATURE_LENGTH} chars",
                        )
                        self.assertLessEqual(len(sig), 60)
                        self.assertTrue(sig.startswith("type=memory|mode="))
                        # Must pass strict signature validation
                        validated = validate_structural_signature(sig)
                        self.assertEqual(sig, validated)

        self.assertEqual(count, 480)

    def test_maximum_long_combination_deterministic_omission(self):
        """When mode + grid + len + theme would exceed 60 chars, theme is deterministically omitted without truncation."""
        inp = MemoryStructuralInput(
            recall_mode="symbol_chronological_order",
            matrix_size="6x6",
            sequence_length_bucket="medium",
            palette_theme="cardinal_directions",
        )
        sig = build_memory_signature(inp)
        # Authoritative type and mode are preserved
        self.assertTrue(sig.startswith("type=memory|mode=symbol_order"))
        # Higher priority optional fields grid and len are preserved
        self.assertIn("grid=6x6", sig)
        self.assertIn("len=medium", sig)
        # Lowest priority optional field theme was omitted because it would exceed 60 chars
        self.assertNotIn("theme=", sig)
        # Value is not truncated
        self.assertNotIn("theme=direct", sig)
        # Total length strictly <= 60
        self.assertLessEqual(len(sig), 60)
        self.assertEqual(sig, "type=memory|mode=symbol_order|grid=6x6|len=medium")

    def test_optional_theme_preserved_when_it_fits(self):
        """When optional fields fit within 60 chars, theme is preserved."""
        # Without matrix_size: symbol_order (29) + len=medium (11) + theme=directions (17) = 57 <= 60
        inp_no_grid = MemoryStructuralInput(
            recall_mode="symbol_chronological_order",
            sequence_length_bucket="medium",
            palette_theme="cardinal_directions",
        )
        sig_no_grid = build_memory_signature(inp_no_grid)
        self.assertIn("theme=directions", sig_no_grid)
        self.assertIn("len=medium", sig_no_grid)
        self.assertLessEqual(len(sig_no_grid), 60)
        self.assertEqual(sig_no_grid, "type=memory|mode=symbol_order|len=medium|theme=directions")

        # Without sequence length: symbol_order (29) + grid=6x6 (9) + theme=directions (17) = 55 <= 60
        inp_no_len = MemoryStructuralInput(
            recall_mode="symbol_chronological_order",
            matrix_size="6x6",
            palette_theme="cardinal_directions",
        )
        sig_no_len = build_memory_signature(inp_no_len)
        self.assertIn("grid=6x6", sig_no_len)
        self.assertIn("theme=directions", sig_no_len)
        self.assertLessEqual(len(sig_no_len), 60)
        self.assertEqual(sig_no_len, "type=memory|mode=symbol_order|grid=6x6|theme=directions")

    def test_required_type_and_mode_never_removed(self):
        inp = MemoryStructuralInput(recall_mode="dynamic_spatial_path")
        sig = build_memory_signature(inp)
        self.assertEqual(sig, "type=memory|mode=dynamic_path")
        self.assertLessEqual(len(sig), 60)


if __name__ == "__main__":
    unittest.main()
