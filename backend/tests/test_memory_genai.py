"""Comprehensive Unit and Safety Test Suite for Phase 4.3 — AI-Generated Memory Challenges.

Ensures:
- Strict non-numeric memory validation (no number guessing, OTPs, PINs, or digit strings).
- Structural numbers are permitted (matrix_size, time limits, integer grid coordinates).
- Coordinate validation without clamping (deterministic out-of-bounds rejection).
- Dynamic spatial path continuity (consecutive steps adjacent, no jumps/stationary steps).
- Strict schema validation with extra="forbid" (no silent repair).
- Independent authoritative answer derivation across all four canonical modes.
- LLM proposed answer consistency checks.
- Personalization duration calibration within difficulty bounds without mutating difficulty.
- Static source analysis proving zero arbitrary code execution primitives.
"""
import ast
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import unittest

from backend.app.core.exceptions import (
    ChallengeContentValidationError,
    GenAIError,
    InvalidChallengeTypeError,
    InvalidDifficultyError,
    MemoryChallengeGenerationError,
    MemoryEvaluationError,
    UnsafePersonalizationContextError,
)
from backend.app.schemas.challenge_content_schemas import (
    SafePersonalizationContext,
    ValidatedChallengeContent,
)
from backend.app.schemas.memory_challenge_schemas import (
    MemoryChallengePayload,
    VALID_RECALL_MODES,
)
from backend.app.services.genai.challenge_constraints import get_challenge_constraints
from backend.app.services.genai.genai_service import GenAIService
from backend.app.services.genai.memory_answer_validator import MemoryAnswerValidator
from backend.app.services.genai.memory_challenge_generator import MemoryChallengeGenerator
from backend.app.services.genai.memory_generation_constraints import (
    EASY_MEMORY_CONSTRAINTS,
    HARD_MEMORY_CONSTRAINTS,
    MEDIUM_MEMORY_CONSTRAINTS,
    build_memory_generation_constraints,
    get_memory_difficulty_constraints,
)
from backend.app.services.genai.memory_prompt_builder import MemoryPromptBuilder
from backend.app.services.genai.mock_provider import MockGenAIProvider


def _create_canned_memory_response(
    challenge_type: str = "memory",
    difficulty_level: str = "easy",
    title: str = "Color Tile Sequence Recall",
    instructions: str = "Memorize the sequence of colored tiles, then recall them in order.",
    payload_dict: Optional[Dict[str, Any]] = None,
    min_duration_seconds: int = 10,
) -> Dict[str, Any]:
    """Helper to generate structured provider output for mock testing."""
    if payload_dict is None:
        payload_dict = {
            "recall_mode": "visual_sequence",
            "sequence_length": 3,
            "display_sequence": ["emerald", "amber", "azure"],
            "palette": ["emerald", "amber", "azure", "coral"],
            "display_duration_seconds": 4,
            "time_limit_seconds": 20,
            "proposed_answer": ["emerald", "amber", "azure"],
        }

    return {
        "challenge_type": challenge_type,
        "difficulty_level": difficulty_level,
        "title": title,
        "instructions": instructions,
        "content_payload": payload_dict,
        "verification_mode": "memory_standard",
        "min_duration_seconds": min_duration_seconds,
    }


class TestMemoryGenAISchemasAndConstraints(unittest.TestCase):
    """Test memory Pydantic schemas and difficulty constraints."""

    def test_memory_payload_valid_visual_sequence(self) -> None:
        payload = MemoryChallengePayload(
            recall_mode="visual_sequence",
            sequence_length=3,
            display_sequence=["emerald", "amber", "azure"],
            palette=["emerald", "amber", "azure", "coral"],
            display_duration_seconds=4,
            time_limit_seconds=20,
            proposed_answer=["emerald", "amber", "azure"],
        )
        self.assertEqual(payload.recall_mode, "visual_sequence")
        self.assertEqual(payload.sequence_length, 3)
        self.assertEqual(payload.display_sequence, ["emerald", "amber", "azure"])

    def test_memory_payload_extra_fields_forbidden(self) -> None:
        # extra="forbid" must reject unexpected fields (Correction 7)
        with self.assertRaises(ValueError) as ctx:
            MemoryChallengePayload(
                recall_mode="visual_sequence",
                display_sequence=["emerald", "amber"],
                unexpected_extra_field="malicious",
            )
        self.assertIn("extra_forbidden", str(ctx.exception))

    def test_memory_payload_invalid_recall_mode(self) -> None:
        with self.assertRaises(ValueError):
            MemoryChallengePayload(
                recall_mode="unsupported_quantum_recall",
                display_sequence=["emerald", "amber"],
            )

    def test_memory_difficulty_constraints_resolution(self) -> None:
        easy = get_memory_difficulty_constraints("easy")
        self.assertEqual(easy.difficulty_level, "easy")
        self.assertIn("visual_sequence", easy.allowed_recall_modes)
        self.assertNotIn("dynamic_spatial_path", easy.allowed_recall_modes)
        self.assertEqual(easy.min_sequence_length, 3)
        self.assertEqual(easy.max_sequence_length, 4)

        med = get_memory_difficulty_constraints("medium")
        self.assertEqual(med.difficulty_level, "medium")
        self.assertIn("dynamic_spatial_path", med.allowed_recall_modes)
        self.assertEqual(med.min_sequence_length, 4)
        self.assertEqual(med.max_sequence_length, 6)

        hard = get_memory_difficulty_constraints("hard")
        self.assertEqual(hard.difficulty_level, "hard")
        self.assertEqual(hard.min_sequence_length, 6)
        self.assertEqual(hard.max_sequence_length, 8)
        self.assertEqual(hard.max_matrix_size, 5)

    def test_invalid_difficulty_rejection(self) -> None:
        with self.assertRaises(InvalidDifficultyError):
            get_memory_difficulty_constraints("adaptive")
        with self.assertRaises(InvalidDifficultyError):
            get_memory_difficulty_constraints("extreme")


class TestMemoryAnswerValidator(unittest.TestCase):
    """Test targeted non-numeric enforcement, coordinate validation, path continuity, and answer derivation."""

    def test_valid_visual_sequence_answer_derivation(self) -> None:
        payload = MemoryChallengePayload(
            recall_mode="visual_sequence",
            sequence_length=3,
            display_sequence=["emerald", "amber", "azure"],
            display_duration_seconds=4,
            time_limit_seconds=20,
        )
        val_payload, expected_ans = MemoryAnswerValidator.validate_and_derive_answer(
            payload, "easy"
        )
        self.assertEqual(expected_ans, ["emerald", "amber", "azure"])

    def test_valid_symbol_chronological_order(self) -> None:
        payload = MemoryChallengePayload(
            recall_mode="symbol_chronological_order",
            sequence_length=5,
            display_sequence=["triangle", "circle", "diamond", "star", "crescent"],
            display_duration_seconds=6,
            time_limit_seconds=35,
        )
        val_payload, expected_ans = MemoryAnswerValidator.validate_and_derive_answer(
            payload, "medium"
        )
        self.assertEqual(expected_ans, ["triangle", "circle", "diamond", "star", "crescent"])

    def test_valid_spatial_pattern_canonical_sorting(self) -> None:
        # Coordinates provided in arbitrary order
        payload = MemoryChallengePayload(
            recall_mode="spatial_pattern_recall",
            matrix_size=3,
            highlighted_cells=[[2, 1], [0, 2], [1, 0]],
            display_duration_seconds=4,
            time_limit_seconds=20,
        )
        val_payload, expected_ans = MemoryAnswerValidator.validate_and_derive_answer(
            payload, "easy"
        )
        # Authoritative answer is canonically sorted
        self.assertEqual(expected_ans, [[0, 2], [1, 0], [2, 1]])

    def test_valid_dynamic_spatial_path(self) -> None:
        # Steps are continuous and adjacent
        payload = MemoryChallengePayload(
            recall_mode="dynamic_spatial_path",
            matrix_size=3,
            path_steps=[[0, 0], [0, 1], [1, 2], [2, 2]],
            display_duration_seconds=5,
            time_limit_seconds=35,
        )
        val_payload, expected_ans = MemoryAnswerValidator.validate_and_derive_answer(
            payload, "medium"
        )
        self.assertEqual(expected_ans, [[0, 0], [0, 1], [1, 2], [2, 2]])

    def test_targeted_numeric_memory_item_rejected(self) -> None:
        # Digit strings in display_sequence must be rejected (Correction 1 & 2)
        payload = MemoryChallengePayload(
            recall_mode="visual_sequence",
            sequence_length=3,
            display_sequence=["emerald", "42", "azure"],
            display_duration_seconds=4,
            time_limit_seconds=20,
        )
        with self.assertRaises(MemoryEvaluationError) as ctx:
            MemoryAnswerValidator.validate_and_derive_answer(payload, "easy")
        self.assertIn("Forbidden numeric memory item '42'", str(ctx.exception))

    def test_pin_otp_digit_string_rejected(self) -> None:
        payload = MemoryChallengePayload(
            recall_mode="visual_sequence",
            sequence_length=4,
            display_sequence=["9", "8", "2", "1"],
            display_duration_seconds=4,
            time_limit_seconds=20,
        )
        with self.assertRaises(MemoryEvaluationError) as ctx:
            MemoryAnswerValidator.validate_and_derive_answer(payload, "easy")
        self.assertIn("Forbidden numeric memory item", str(ctx.exception))

    def test_arithmetic_expression_item_rejected(self) -> None:
        payload = MemoryChallengePayload(
            recall_mode="visual_sequence",
            sequence_length=3,
            display_sequence=["emerald", "5 + 4", "azure"],
            display_duration_seconds=4,
            time_limit_seconds=20,
        )
        with self.assertRaises(MemoryEvaluationError) as ctx:
            MemoryAnswerValidator.validate_and_derive_answer(payload, "easy")
        self.assertIn("Forbidden arithmetic expression", str(ctx.exception))

    def test_context_aware_forbidden_phrase_rejected(self) -> None:
        # Rejects phrases like "guess the number", "pin code", "otp" (Correction 4)
        with self.assertRaises(MemoryEvaluationError) as ctx:
            MemoryAnswerValidator.scan_for_forbidden_numeric_concepts(
                "Memorize the secret PIN code and enter it."
            )
        self.assertIn("pin code", str(ctx.exception))

        with self.assertRaises(MemoryEvaluationError) as ctx:
            MemoryAnswerValidator.scan_for_forbidden_numeric_concepts(
                "Play this guess the number game to wake up."
            )
        self.assertIn("guess the number", str(ctx.exception))

    def test_ordinary_words_code_and_guess_allowed_in_non_numeric_context(self) -> None:
        # Common words without numeric context are not blanket rejected (Correction 4)
        # Should not raise exception
        MemoryAnswerValidator.scan_for_forbidden_numeric_concepts(
            "Try not to guess blindly, observe the colors carefully."
        )
        MemoryAnswerValidator.scan_for_forbidden_numeric_concepts(
            "Color code matching challenge."
        )

    def test_out_of_bounds_coordinate_rejected_no_clamping(self) -> None:
        # Coordinate [3, 1] is out of bounds for 3x3 grid (valid is 0..2). Must reject, NOT clamp!
        payload = MemoryChallengePayload(
            recall_mode="spatial_pattern_recall",
            matrix_size=3,
            highlighted_cells=[[0, 0], [1, 1], [3, 1]],  # [3, 1] out of bounds
            display_duration_seconds=4,
            time_limit_seconds=20,
        )
        with self.assertRaises(MemoryEvaluationError) as ctx:
            MemoryAnswerValidator.validate_and_derive_answer(payload, "easy")
        self.assertIn("out of bounds for matrix_size 3", str(ctx.exception))

    def test_negative_coordinate_rejected_no_clamping(self) -> None:
        payload = MemoryChallengePayload(
            recall_mode="spatial_pattern_recall",
            matrix_size=3,
            highlighted_cells=[[0, 0], [-1, 1], [1, 2]],
            display_duration_seconds=4,
            time_limit_seconds=20,
        )
        with self.assertRaises(MemoryEvaluationError) as ctx:
            MemoryAnswerValidator.validate_and_derive_answer(payload, "easy")
        self.assertIn("out of bounds", str(ctx.exception))

    def test_duplicate_spatial_cell_rejected(self) -> None:
        payload = MemoryChallengePayload(
            recall_mode="spatial_pattern_recall",
            matrix_size=3,
            highlighted_cells=[[0, 1], [1, 2], [0, 1]],  # Duplicate [0, 1]
            display_duration_seconds=4,
            time_limit_seconds=20,
        )
        with self.assertRaises(MemoryEvaluationError) as ctx:
            MemoryAnswerValidator.validate_and_derive_answer(payload, "easy")
        self.assertIn("Duplicate cell coordinate [0, 1]", str(ctx.exception))

    def test_dynamic_path_non_adjacent_jump_rejected(self) -> None:
        # Step from [0, 0] to [0, 2] is a jump of distance 2 (Correction 3)
        payload = MemoryChallengePayload(
            recall_mode="dynamic_spatial_path",
            matrix_size=3,
            path_steps=[[0, 0], [0, 2], [1, 2], [2, 2]],
            display_duration_seconds=5,
            time_limit_seconds=35,
        )
        with self.assertRaises(MemoryEvaluationError) as ctx:
            MemoryAnswerValidator.validate_and_derive_answer(payload, "medium")
        self.assertIn("Non-adjacent step jump detected", str(ctx.exception))

    def test_dynamic_path_stationary_step_rejected(self) -> None:
        payload = MemoryChallengePayload(
            recall_mode="dynamic_spatial_path",
            matrix_size=3,
            path_steps=[[0, 0], [0, 0], [0, 1], [1, 1]],
            display_duration_seconds=5,
            time_limit_seconds=35,
        )
        with self.assertRaises(MemoryEvaluationError) as ctx:
            MemoryAnswerValidator.validate_and_derive_answer(payload, "medium")
        self.assertIn("Duplicate step [0, 0]", str(ctx.exception))

    def test_dynamic_path_not_allowed_in_easy(self) -> None:
        payload = MemoryChallengePayload(
            recall_mode="dynamic_spatial_path",
            matrix_size=3,
            path_steps=[[0, 0], [0, 1], [1, 1]],
            display_duration_seconds=4,
            time_limit_seconds=20,
        )
        with self.assertRaises(MemoryEvaluationError) as ctx:
            MemoryAnswerValidator.validate_and_derive_answer(payload, "easy")
        self.assertIn("Recall mode 'dynamic_spatial_path' is not permitted for difficulty 'easy'", str(ctx.exception))

    def test_sequence_length_exceeded_rejected(self) -> None:
        # Easy allows max 4 items
        payload = MemoryChallengePayload(
            recall_mode="visual_sequence",
            sequence_length=7,
            display_sequence=["a", "b", "c", "d", "e", "f", "g"],
            display_duration_seconds=4,
            time_limit_seconds=20,
        )
        with self.assertRaises(MemoryEvaluationError) as ctx:
            MemoryAnswerValidator.validate_and_derive_answer(payload, "easy")
        self.assertIn("outside permitted range", str(ctx.exception))

    def test_llm_proposed_answer_correct_accepted(self) -> None:
        payload = MemoryChallengePayload(
            recall_mode="visual_sequence",
            sequence_length=3,
            display_sequence=["emerald", "amber", "azure"],
            display_duration_seconds=4,
            time_limit_seconds=20,
            proposed_answer=["emerald", "amber", "azure"],
        )
        val_payload, expected_ans = MemoryAnswerValidator.validate_and_derive_answer(
            payload, "easy"
        )
        self.assertEqual(expected_ans, ["emerald", "amber", "azure"])

    def test_llm_proposed_answer_mismatch_rejected(self) -> None:
        # LLM proposes wrong sequence order (hallucinated)
        payload = MemoryChallengePayload(
            recall_mode="visual_sequence",
            sequence_length=3,
            display_sequence=["emerald", "amber", "azure"],
            display_duration_seconds=4,
            time_limit_seconds=20,
            proposed_answer=["amber", "emerald", "azure"],
        )
        with self.assertRaises(MemoryEvaluationError) as ctx:
            MemoryAnswerValidator.validate_and_derive_answer(payload, "easy")
        self.assertIn("LLM proposed answer", str(ctx.exception))
        self.assertIn("conflicts with derived authoritative answer", str(ctx.exception))

    def test_spatial_pattern_proposed_answer_set_comparison(self) -> None:
        # Spatial pattern proposed answer matches even if ordering differs
        payload = MemoryChallengePayload(
            recall_mode="spatial_pattern_recall",
            matrix_size=3,
            highlighted_cells=[[0, 1], [1, 2], [2, 0]],
            display_duration_seconds=4,
            time_limit_seconds=20,
            proposed_answer=[[2, 0], [0, 1], [1, 2]],
        )
        val_payload, expected_ans = MemoryAnswerValidator.validate_and_derive_answer(
            payload, "easy"
        )
        self.assertEqual(expected_ans, [[0, 1], [1, 2], [2, 0]])


class TestMemoryPromptBuilder(unittest.TestCase):
    """Test prompt building and personalization context scaling."""

    def test_duration_affects_sequence_length_strictly_within_tier_bounds(self) -> None:
        # Easy range is [3, 4]. Short duration (5s) gives 3, long duration (60s) gives 4
        ctx_short = SafePersonalizationContext(desired_duration_seconds=5)
        req_short = MemoryPromptBuilder.build_request("easy", ctx_short)
        self.assertEqual(req_short.context_payload["target_item_count"], 3)

        ctx_long = SafePersonalizationContext(desired_duration_seconds=60)
        req_long = MemoryPromptBuilder.build_request("easy", ctx_long)
        self.assertEqual(req_long.context_payload["target_item_count"], 4)

    def test_difficulty_remains_immutable_despite_duration(self) -> None:
        # Duration preference must never escalate or downgrade difficulty (Correction 5)
        ctx = SafePersonalizationContext(desired_duration_seconds=5)
        req = MemoryPromptBuilder.build_request("hard", ctx)
        self.assertEqual(req.difficulty_level, "hard")
        self.assertIn("Difficulty is strictly locked to 'hard'", req.custom_instructions)

    def test_identity_exclusion_in_prompt(self) -> None:
        ctx = SafePersonalizationContext(preferred_theme="Cosmic Nebula")
        req = MemoryPromptBuilder.build_request("medium", ctx)
        self.assertIsNone(req.user_id)
        context_keys = [k.lower() for k in req.context_payload.keys()]
        for forbidden in ("user_id", "email", "session_id", "alarm_id", "password"):
            self.assertNotIn(forbidden, context_keys)
            self.assertNotIn(forbidden, req.custom_instructions.lower())


class TestMemoryChallengeGenerator(unittest.TestCase):
    """Test end-to-end memory challenge generation and framework validation."""

    def test_generate_easy_visual_sequence(self) -> None:
        canned = _create_canned_memory_response(
            challenge_type="memory",
            difficulty_level="easy",
            payload_dict={
                "recall_mode": "visual_sequence",
                "sequence_length": 3,
                "display_sequence": ["emerald", "amber", "azure"],
                "palette": ["emerald", "amber", "azure", "coral"],
                "display_duration_seconds": 4,
                "time_limit_seconds": 20,
                "proposed_answer": ["emerald", "amber", "azure"],
            },
        )
        mock_provider = MockGenAIProvider(canned_content=canned)
        service = GenAIService(provider=mock_provider, enabled=True)
        generator = MemoryChallengeGenerator(service)

        validated: ValidatedChallengeContent = generator.generate_memory_challenge("easy")

        self.assertEqual(validated.challenge_type, "memory")
        self.assertEqual(validated.difficulty_level, "easy")
        self.assertEqual(validated.verification_mode, "memory_standard")
        self.assertEqual(validated.expected_answer, ["emerald", "amber", "azure"])
        self.assertTrue(validated.generation_metadata["authoritative_answer_derived"])
        self.assertEqual(validated.generation_metadata["recall_mode"], "visual_sequence")

    def test_generate_medium_dynamic_spatial_path(self) -> None:
        canned = _create_canned_memory_response(
            challenge_type="memory",
            difficulty_level="medium",
            payload_dict={
                "recall_mode": "dynamic_spatial_path",
                "matrix_size": 3,
                "path_steps": [[0, 0], [0, 1], [1, 1], [2, 1], [2, 2]],
                "display_duration_seconds": 5,
                "time_limit_seconds": 35,
                "proposed_answer": [[0, 0], [0, 1], [1, 1], [2, 1], [2, 2]],
            },
        )
        mock_provider = MockGenAIProvider(canned_content=canned)
        service = GenAIService(provider=mock_provider, enabled=True)
        generator = MemoryChallengeGenerator(service)

        validated = generator.generate_memory_challenge("medium")
        self.assertEqual(
            validated.expected_answer, [[0, 0], [0, 1], [1, 1], [2, 1], [2, 2]]
        )

    def test_generate_hard_spatial_pattern(self) -> None:
        canned = _create_canned_memory_response(
            challenge_type="memory",
            difficulty_level="hard",
            payload_dict={
                "recall_mode": "spatial_pattern_recall",
                "matrix_size": 4,
                "highlighted_cells": [[0, 1], [1, 2], [2, 3], [3, 0], [1, 0], [2, 2]],
                "display_duration_seconds": 7,
                "time_limit_seconds": 50,
                "proposed_answer": [[0, 1], [1, 0], [1, 2], [2, 2], [2, 3], [3, 0]],
            },
        )
        mock_provider = MockGenAIProvider(canned_content=canned)
        service = GenAIService(provider=mock_provider, enabled=True)
        generator = MemoryChallengeGenerator(service)

        validated = generator.generate_memory_challenge("hard")
        self.assertEqual(
            validated.expected_answer,
            [[0, 1], [1, 0], [1, 2], [2, 2], [2, 3], [3, 0]],
        )

    def test_difficulty_immutability_enforced(self) -> None:
        generator = MemoryChallengeGenerator(GenAIService(provider=MockGenAIProvider(), enabled=True))
        with self.assertRaises(InvalidDifficultyError):
            generator.generate_memory_challenge("adaptive")

    def test_challenge_type_immutability_enforced(self) -> None:
        generator = MemoryChallengeGenerator(GenAIService(provider=MockGenAIProvider(), enabled=True))
        with self.assertRaises(InvalidChallengeTypeError):
            generator.generate_memory_challenge("easy", challenge_type="math")

    def test_unsafe_personalization_context_rejected(self) -> None:
        generator = MemoryChallengeGenerator(GenAIService(provider=MockGenAIProvider(), enabled=True))
        with self.assertRaises(UnsafePersonalizationContextError):
            generator.generate_memory_challenge("easy", raw_context={"user_id": 999})

    def test_malformed_provider_response_rejected(self) -> None:
        mock_provider = MockGenAIProvider(canned_content={"malformed": "not a dictionary"})
        service = GenAIService(provider=mock_provider, enabled=True)
        generator = MemoryChallengeGenerator(service)

        with self.assertRaises(ChallengeContentValidationError):
            generator.generate_memory_challenge("easy")

    def test_exception_hierarchy(self) -> None:
        self.assertTrue(issubclass(MemoryEvaluationError, ChallengeContentValidationError))
        self.assertTrue(issubclass(MemoryEvaluationError, GenAIError))

        self.assertTrue(issubclass(MemoryChallengeGenerationError, GenAIError))
        self.assertFalse(issubclass(MemoryChallengeGenerationError, ChallengeContentValidationError))


class TestPhase43StaticSafetyAudit(unittest.TestCase):
    """Static source code safety audit to verify zero arbitrary execution primitives."""

    def test_no_eval_or_exec_in_memory_genai_files(self) -> None:
        """Inspect Phase 4.3 files and assert zero executable calls to eval, exec, subprocess, os.system."""
        forbidden_calls = {"eval", "exec", "compile", "__import__"}
        forbidden_modules = {"subprocess", "os.system"}

        phase_43_files = [
            Path("backend/app/schemas/memory_challenge_schemas.py"),
            Path("backend/app/services/genai/memory_generation_constraints.py"),
            Path("backend/app/services/genai/memory_answer_validator.py"),
            Path("backend/app/services/genai/memory_prompt_builder.py"),
            Path("backend/app/services/genai/memory_challenge_generator.py"),
        ]

        for file_path in phase_43_files:
            self.assertTrue(file_path.exists(), f"File {file_path} must exist.")
            content = file_path.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(file_path))

            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        self.assertNotIn(
                            node.func.id,
                            forbidden_calls,
                            f"Forbidden function '{node.func.id}' called in {file_path} at line {node.lineno}",
                        )
                    elif isinstance(node.func, ast.Attribute):
                        attr_chain = f"{getattr(node.func.value, 'id', '')}.{node.func.attr}"
                        self.assertNotIn(
                            attr_chain,
                            forbidden_modules,
                            f"Forbidden call '{attr_chain}' in {file_path} at line {node.lineno}",
                        )
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            self.assertNotEqual(alias.name, "subprocess", f"subprocess import in {file_path}")
                    elif isinstance(node, ast.ImportFrom):
                        self.assertNotEqual(node.module, "subprocess", f"subprocess import in {file_path}")


if __name__ == "__main__":
    unittest.main()
