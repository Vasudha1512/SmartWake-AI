

"""Unit tests for Phase 3.3.2 — Safety Guardrails & Cold-Start Rules.

Verifies:
1. ColdStartRouter lifecycle stages (Stage 0 heuristic, Stage 1 contextual rules, Stage 2 ML handoff).
2. SafetyGuardrails operational boundaries (maximum step-shift, sleep inertia floor, metadata).
3. Precedence order and boundary conditions.
"""
import unittest

from backend.app.schemas.personalization_schemas import (
    DecisionSource,
    DifficultyLevel,
    PersonalizationContext,
)
from backend.app.services.personalization_engine import (
    ColdStartResult,
    ColdStartRouter,
    GuardrailResult,
    SafetyGuardrails,
)


class TestColdStartRouter(unittest.TestCase):
    """Test suite for ColdStartRouter lifecycle stages and rules."""

    def test_stage_0_math_defaults_to_easy(self):
        """Stage 0 high-cognitive challenge 'math' must default to easy."""
        ctx = PersonalizationContext(
            user_id=1,
            wake_session_id=10,
            challenge_type="math",
            historical_session_count=0,
            current_session_snooze_count=0,
        )
        res = ColdStartRouter.route(ctx)
        self.assertEqual(res.stage, 0)
        self.assertFalse(res.requires_ml)
        self.assertEqual(res.candidate_difficulty, "easy")
        self.assertEqual(res.decision_source, DecisionSource.COLD_START_STAGE_0)
        self.assertIn("high-cognitive", str(res.rule_reason))
        # Challenge type remains unchanged
        self.assertEqual(ctx.challenge_type, "math")

    def test_stage_0_memory_defaults_to_easy(self):
        """Stage 0 high-cognitive challenge 'memory' must default to easy."""
        ctx = PersonalizationContext(
            user_id=1,
            wake_session_id=11,
            challenge_type="memory",
            historical_session_count=2,
            current_session_snooze_count=1,
        )
        res = ColdStartRouter.route(ctx)
        self.assertEqual(res.stage, 0)
        self.assertFalse(res.requires_ml)
        self.assertEqual(res.candidate_difficulty, "easy")
        self.assertEqual(res.decision_source, DecisionSource.COLD_START_STAGE_0)

    def test_stage_0_dance_defaults_to_medium(self):
        """Stage 0 physical challenge 'dance' must default to medium."""
        ctx = PersonalizationContext(
            user_id=1,
            wake_session_id=12,
            challenge_type="dance",
            historical_session_count=1,
            current_session_snooze_count=0,
        )
        res = ColdStartRouter.route(ctx)
        self.assertEqual(res.stage, 0)
        self.assertEqual(res.candidate_difficulty, "medium")
        self.assertEqual(res.decision_source, DecisionSource.COLD_START_STAGE_0)

    def test_stage_0_tongue_twister_defaults_to_medium(self):
        """Stage 0 speech challenge 'tongue_twister' must default to medium."""
        ctx = PersonalizationContext(
            user_id=1,
            wake_session_id=13,
            challenge_type="tongue_twister",
            historical_session_count=3,
            current_session_snooze_count=0,
        )
        res = ColdStartRouter.route(ctx)
        self.assertEqual(res.stage, 0)
        self.assertEqual(res.candidate_difficulty, "medium")

    def test_stage_0_push_ups_defaults_to_medium(self):
        """Stage 0 physical challenge 'push_ups' must default to medium."""
        ctx = PersonalizationContext(
            user_id=1,
            wake_session_id=14,
            challenge_type="push_ups",
            historical_session_count=2,
            current_session_snooze_count=0,
        )
        res = ColdStartRouter.route(ctx)
        self.assertEqual(res.stage, 0)
        self.assertEqual(res.candidate_difficulty, "medium")

    def test_stage_0_snooze_downgrade_to_easy(self):
        """Stage 0 physical/speech tasks downgrade to easy when snooze count >= 2."""
        for ctype in ["dance", "tongue_twister", "push_ups"]:
            # With 1 snooze: stays medium
            ctx_1 = PersonalizationContext(
                user_id=1,
                wake_session_id=15,
                challenge_type=ctype,
                historical_session_count=1,
                current_session_snooze_count=1,
            )
            res_1 = ColdStartRouter.route(ctx_1)
            self.assertEqual(res_1.candidate_difficulty, "medium")

            # With exactly 2 snoozes: downgrades to easy
            ctx_2 = PersonalizationContext(
                user_id=1,
                wake_session_id=16,
                challenge_type=ctype,
                historical_session_count=1,
                current_session_snooze_count=2,
            )
            res_2 = ColdStartRouter.route(ctx_2)
            self.assertEqual(res_2.candidate_difficulty, "easy")
            self.assertIn("Downgraded to 'easy'", str(res_2.rule_reason))

            # With > 2 snoozes: remains easy
            ctx_3 = PersonalizationContext(
                user_id=1,
                wake_session_id=17,
                challenge_type=ctype,
                historical_session_count=1,
                current_session_snooze_count=4,
            )
            res_3 = ColdStartRouter.route(ctx_3)
            self.assertEqual(res_3.candidate_difficulty, "easy")

    def test_stage_1_promotion_on_mastery(self):
        """Stage 1: 100% success rate AND completion time < 15s promotes by +1 level."""
        # Medium baseline promotes to hard
        ctx_med = PersonalizationContext(
            user_id=1,
            wake_session_id=20,
            challenge_type="dance",
            historical_session_count=5,
            previous_difficulty="medium",
        )
        res_med = ColdStartRouter.route(
            ctx_med,
            recent_success_rate=1.0,
            recent_avg_duration_seconds=12.5,
            has_recent_failure=False,
        )
        self.assertEqual(res_med.stage, 1)
        self.assertEqual(res_med.candidate_difficulty, "hard")
        self.assertEqual(res_med.decision_source, DecisionSource.COLD_START_STAGE_1)
        self.assertIn("promotes baseline 'medium' to 'hard'", str(res_med.rule_reason))

        # Easy baseline promotes to medium
        ctx_easy = PersonalizationContext(
            user_id=1,
            wake_session_id=21,
            challenge_type="math",
            historical_session_count=4,
            previous_difficulty="easy",
        )
        res_easy = ColdStartRouter.route(
            ctx_easy,
            recent_success_rate=1.0,
            recent_avg_duration_seconds=11.0,
            has_recent_failure=False,
        )
        self.assertEqual(res_easy.candidate_difficulty, "medium")

        # Hard baseline stays hard (capped at hard)
        ctx_hard = PersonalizationContext(
            user_id=1,
            wake_session_id=22,
            challenge_type="push_ups",
            historical_session_count=6,
            previous_difficulty="hard",
        )
        res_hard = ColdStartRouter.route(
            ctx_hard,
            recent_success_rate=1.0,
            recent_avg_duration_seconds=9.0,
            has_recent_failure=False,
        )
        self.assertEqual(res_hard.candidate_difficulty, "hard")

    def test_stage_1_recent_failure_resolves_to_easy(self):
        """Stage 1: Recent failure resolves to easy."""
        ctx = PersonalizationContext(
            user_id=1,
            wake_session_id=23,
            challenge_type="memory",
            historical_session_count=5,
            previous_difficulty="medium",
        )
        res = ColdStartRouter.route(
            ctx,
            recent_success_rate=0.67,
            recent_avg_duration_seconds=14.0,
            has_recent_failure=True,
        )
        self.assertEqual(res.stage, 1)
        self.assertEqual(res.candidate_difficulty, "easy")
        self.assertIn("recent failure occurred", str(res.rule_reason))

    def test_stage_1_slow_completion_resolves_to_easy(self):
        """Stage 1: Slow completion (> 40s) resolves to easy even if success rate was high."""
        ctx = PersonalizationContext(
            user_id=1,
            wake_session_id=24,
            challenge_type="math",
            historical_session_count=6,
            previous_difficulty="hard",
        )
        res = ColdStartRouter.route(
            ctx,
            recent_success_rate=1.0,
            recent_avg_duration_seconds=42.5,
            has_recent_failure=False,
        )
        self.assertEqual(res.stage, 1)
        self.assertEqual(res.candidate_difficulty, "easy")
        self.assertIn("slow completion time", str(res.rule_reason))

    def test_stage_1_neutral_performance_resolves_to_medium(self):
        """Stage 1: Balanced engagement (neither fast+100% nor slow/failing) resolves to medium."""
        ctx = PersonalizationContext(
            user_id=1,
            wake_session_id=25,
            challenge_type="tongue_twister",
            historical_session_count=7,
            previous_difficulty="medium",
        )
        res = ColdStartRouter.route(
            ctx,
            recent_success_rate=0.75,
            recent_avg_duration_seconds=22.0,
            has_recent_failure=False,
        )
        self.assertEqual(res.stage, 1)
        self.assertEqual(res.candidate_difficulty, "medium")
        self.assertIn("standard balanced engagement", str(res.rule_reason))

    def test_stage_2_clearly_indicates_ml_required(self):
        """Stage 2 (8+ sessions) must return requires_ml=True without setting candidate_difficulty."""
        for count in [8, 9, 20, 100]:
            ctx = PersonalizationContext(
                user_id=1,
                wake_session_id=30,
                challenge_type="dance",
                historical_session_count=count,
            )
            res = ColdStartRouter.route(ctx)
            self.assertEqual(res.stage, 2)
            self.assertTrue(res.requires_ml)
            self.assertIsNone(res.candidate_difficulty)
            self.assertIsNone(res.decision_source)
            self.assertIn("requires ML baseline model inference", str(res.rule_reason))

    def test_lifecycle_boundaries(self):
        """Test exact boundary transitions for cold start stages."""
        # 3 sessions is Stage 0; 4 sessions is Stage 1
        self.assertEqual(ColdStartRouter.get_stage(3), 0)
        self.assertEqual(ColdStartRouter.get_stage(4), 1)

        # 7 sessions is Stage 1; 8 sessions is Stage 2
        self.assertEqual(ColdStartRouter.get_stage(7), 1)
        self.assertEqual(ColdStartRouter.get_stage(8), 2)

    def test_stage_1_duration_boundaries(self):
        """Test duration boundary values in Stage 1: exactly 15.0s and exactly 40.0s."""
        ctx = PersonalizationContext(
            user_id=1,
            wake_session_id=35,
            challenge_type="math",
            historical_session_count=5,
            previous_difficulty="medium",
        )

        # Fast completion threshold is strictly < 15.0s:
        # At exactly 15.0s, it does NOT qualify for promotion (remains neutral medium)
        res_15 = ColdStartRouter.route(
            ctx,
            recent_success_rate=1.0,
            recent_avg_duration_seconds=15.0,
            has_recent_failure=False,
        )
        self.assertEqual(res_15.candidate_difficulty, "medium")

        # At 14.9s (< 15.0s), it qualifies for promotion
        res_14_9 = ColdStartRouter.route(
            ctx,
            recent_success_rate=1.0,
            recent_avg_duration_seconds=14.9,
            has_recent_failure=False,
        )
        self.assertEqual(res_14_9.candidate_difficulty, "hard")

        # Slow completion threshold is strictly > 40.0s:
        # At exactly 40.0s, it does NOT trigger demotion (remains neutral medium)
        res_40 = ColdStartRouter.route(
            ctx,
            recent_success_rate=0.8,
            recent_avg_duration_seconds=40.0,
            has_recent_failure=False,
        )
        self.assertEqual(res_40.candidate_difficulty, "medium")

        # At 40.1s (> 40.0s), it triggers demotion to easy
        res_40_1 = ColdStartRouter.route(
            ctx,
            recent_success_rate=0.8,
            recent_avg_duration_seconds=40.1,
            has_recent_failure=False,
        )
        self.assertEqual(res_40_1.candidate_difficulty, "easy")


class TestSafetyGuardrails(unittest.TestCase):
    """Test suite for SafetyGuardrails operational limits and precedence."""

    def test_step_shift_easy_to_hard_clamped_to_medium(self):
        """Candidate 'hard' with previous 'easy' (+2 shift) must be clamped to 'medium'."""
        res = SafetyGuardrails.apply_guardrails(
            candidate_difficulty="hard",
            previous_difficulty="easy",
            current_session_snooze_count=0,
        )
        self.assertEqual(res.final_difficulty, "medium")
        self.assertEqual(res.raw_difficulty, "hard")
        self.assertTrue(res.guardrail_applied)
        self.assertTrue(res.step_shift_applied)
        self.assertFalse(res.sleep_inertia_applied)
        self.assertIn("Maximum step shift clamped", str(res.guardrail_reason))

    def test_step_shift_hard_to_easy_clamped_to_medium(self):
        """Candidate 'easy' with previous 'hard' (-2 shift) must be clamped to 'medium'."""
        res = SafetyGuardrails.apply_guardrails(
            candidate_difficulty="easy",
            previous_difficulty="hard",
            current_session_snooze_count=0,
        )
        self.assertEqual(res.final_difficulty, "medium")
        self.assertEqual(res.raw_difficulty, "easy")
        self.assertTrue(res.guardrail_applied)
        self.assertTrue(res.step_shift_applied)
        self.assertFalse(res.sleep_inertia_applied)

    def test_step_shift_medium_to_hard_remains_hard(self):
        """Candidate 'hard' with previous 'medium' (+1 shift) is allowed."""
        res = SafetyGuardrails.apply_guardrails(
            candidate_difficulty="hard",
            previous_difficulty="medium",
            current_session_snooze_count=0,
        )
        self.assertEqual(res.final_difficulty, "hard")
        self.assertFalse(res.guardrail_applied)
        self.assertFalse(res.step_shift_applied)
        self.assertIsNone(res.guardrail_reason)

    def test_step_shift_medium_to_easy_remains_easy(self):
        """Candidate 'easy' with previous 'medium' (-1 shift) is allowed."""
        res = SafetyGuardrails.apply_guardrails(
            candidate_difficulty="easy",
            previous_difficulty="medium",
            current_session_snooze_count=0,
        )
        self.assertEqual(res.final_difficulty, "easy")
        self.assertFalse(res.guardrail_applied)
        self.assertFalse(res.step_shift_applied)

    def test_step_shift_same_difficulty_remains_unchanged(self):
        """Candidate identical to previous is allowed."""
        for diff in ["easy", "medium", "hard"]:
            res = SafetyGuardrails.apply_guardrails(
                candidate_difficulty=diff,
                previous_difficulty=diff,
                current_session_snooze_count=0,
            )
            self.assertEqual(res.final_difficulty, diff)
            self.assertFalse(res.guardrail_applied)

    def test_sleep_inertia_floor_at_3_snoozes(self):
        """Candidate 'hard' with current_session_snooze_count >= 3 is capped to 'medium'."""
        # 2 snoozes: remains hard
        res_2 = SafetyGuardrails.apply_guardrails(
            candidate_difficulty="hard",
            previous_difficulty="hard",
            current_session_snooze_count=2,
        )
        self.assertEqual(res_2.final_difficulty, "hard")
        self.assertFalse(res_2.guardrail_applied)

        # Exactly 3 snoozes: capped to medium
        res_3 = SafetyGuardrails.apply_guardrails(
            candidate_difficulty="hard",
            previous_difficulty="hard",
            current_session_snooze_count=3,
        )
        self.assertEqual(res_3.final_difficulty, "medium")
        self.assertTrue(res_3.guardrail_applied)
        self.assertTrue(res_3.sleep_inertia_applied)
        self.assertIn("Sleep inertia floor applied", str(res_3.guardrail_reason))

        # > 3 snoozes: capped to medium
        res_5 = SafetyGuardrails.apply_guardrails(
            candidate_difficulty="hard",
            previous_difficulty="hard",
            current_session_snooze_count=5,
        )
        self.assertEqual(res_5.final_difficulty, "medium")
        self.assertTrue(res_5.sleep_inertia_applied)

    def test_sleep_inertia_floor_easy_remains_easy(self):
        """Candidate 'easy' with current_session_snooze_count >= 3 remains 'easy'."""
        res = SafetyGuardrails.apply_guardrails(
            candidate_difficulty="easy",
            previous_difficulty="easy",
            current_session_snooze_count=4,
        )
        self.assertEqual(res.final_difficulty, "easy")
        self.assertFalse(res.guardrail_applied)
        self.assertFalse(res.sleep_inertia_applied)

    def test_sleep_inertia_floor_medium_remains_medium(self):
        """Candidate 'medium' with current_session_snooze_count >= 3 remains 'medium'."""
        res = SafetyGuardrails.apply_guardrails(
            candidate_difficulty="medium",
            previous_difficulty="medium",
            current_session_snooze_count=3,
        )
        self.assertEqual(res.final_difficulty, "medium")
        self.assertFalse(res.guardrail_applied)

    def test_no_previous_difficulty_skips_step_shift(self):
        """When previous_difficulty is None, step shift clamp is skipped."""
        res = SafetyGuardrails.apply_guardrails(
            candidate_difficulty="hard",
            previous_difficulty=None,
            current_session_snooze_count=0,
        )
        self.assertEqual(res.final_difficulty, "hard")
        self.assertFalse(res.guardrail_applied)

    def test_combined_guardrail_precedence(self):
        """Test when candidate is hard, previous is easy, and snooze count is >= 3.

        Precedence:
        1. Step shift clamps easy -> hard to medium.
        2. Sleep inertia floor evaluates medium (already <= medium, remains medium).
        """
        res = SafetyGuardrails.apply_guardrails(
            candidate_difficulty="hard",
            previous_difficulty="easy",
            current_session_snooze_count=3,
        )
        self.assertEqual(res.final_difficulty, "medium")
        self.assertEqual(res.raw_difficulty, "hard")
        self.assertTrue(res.guardrail_applied)
        self.assertTrue(res.step_shift_applied)
        # Sleep inertia did not need to clamp because step shift already resolved to medium
        self.assertFalse(res.sleep_inertia_applied)

    def test_invalid_candidate_difficulty_raises_error(self):
        """Invalid candidate difficulty raises ValueError."""
        with self.assertRaises(ValueError):
            SafetyGuardrails.apply_guardrails(
                candidate_difficulty="super_hard",
                previous_difficulty="medium",
            )


if __name__ == "__main__":
    unittest.main()
