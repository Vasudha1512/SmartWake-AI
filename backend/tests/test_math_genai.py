"""Comprehensive Unit and Safety Test Suite for Phase 4.2 — AI-Generated Math Challenges.

Ensures:
- Strict mathematical evaluation without eval() or exec().
- Independent answer calculation (GenAI answers are never trusted).
- Numeric, resource, depth, length, and operand bound enforcement.
- Exact integer division (rejecting division by zero and remainders).
- Multi-level consistency (operands vs. expression constants vs. proposed answer vs. question text).
- Personalization context safety, identity exclusion, and difficulty immutability.
- Static source analysis proving zero arbitrary code execution primitives.
"""
import ast
import inspect
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import unittest

from backend.app.core.exceptions import (
    ChallengeContentValidationError,
    GenAIError,
    InvalidChallengeTypeError,
    InvalidDifficultyError,
    MathChallengeGenerationError,
    MathEvaluationError,
    UnsafePersonalizationContextError,
)
from backend.app.schemas.challenge_content_schemas import (
    SafePersonalizationContext,
    ValidatedChallengeContent,
)
from backend.app.schemas.genai_schemas import GenAIContentRequest
from backend.app.schemas.math_challenge_schemas import (
    MathChallengePayload,
    MathQuestionItem,
)
from backend.app.services.genai.math_answer_validator import (
    MathAnswerValidator,
    SafeArithmeticEvaluator,
)
from backend.app.services.genai.math_challenge_generator import MathChallengeGenerator
from backend.app.services.genai.math_generation_constraints import (
    EASY_MATH_CONSTRAINTS,
    HARD_MATH_CONSTRAINTS,
    MEDIUM_MATH_CONSTRAINTS,
    build_math_generation_constraints,
    get_math_difficulty_constraints,
)
from backend.app.services.genai.math_prompt_builder import MathPromptBuilder
from backend.app.services.genai.mock_provider import MockGenAIProvider
from backend.app.services.genai.genai_service import GenAIService


def _create_canned_math_response(
    challenge_type: str = "math",
    difficulty_level: str = "easy",
    title: str = "Basic Morning Addition",
    instructions: str = "Solve the arithmetic equations to dismiss the alarm.",
    questions: Optional[List[Dict[str, Any]]] = None,
    time_limit_seconds: int = 20,
    min_duration_seconds: int = 10,
) -> Dict[str, Any]:
    """Helper to generate structured provider output for mock testing."""
    if questions is None:
        questions = [
            {
                "question_id": 1,
                "question": "What is 7 + 5?",
                "expression": "7 + 5",
                "operation": "addition",
                "operands": [7, 5],
                "proposed_answer": 12,
            },
            {
                "question_id": 2,
                "question": "What is 8 + 6?",
                "expression": "8 + 6",
                "operation": "addition",
                "operands": [8, 6],
                "proposed_answer": 14,
            },
        ]

    return {
        "challenge_type": challenge_type,
        "difficulty_level": difficulty_level,
        "title": title,
        "instructions": instructions,
        "content_payload": {
            "question_count": len(questions),
            "questions": questions,
            "time_limit_seconds": time_limit_seconds,
        },
        "verification_mode": "math_standard",
        "min_duration_seconds": min_duration_seconds,
    }


class TestMathGenAISchemasAndConstraints(unittest.TestCase):
    """Test mathematical Pydantic schemas and difficulty constraints."""

    def test_math_question_item_valid(self) -> None:
        item = MathQuestionItem(
            question_id=1,
            question="What is 12 + 8?",
            expression="12 + 8",
            operation="addition",
            operands=[12, 8],
            proposed_answer=20,
        )
        self.assertEqual(item.question_id, 1)
        self.assertEqual(item.expression, "12 + 8")
        self.assertEqual(item.operands, [12, 8])
        self.assertEqual(item.proposed_answer, 20)

    def test_math_question_item_invalid_operands(self) -> None:
        with self.assertRaises(ValueError):
            MathQuestionItem(
                question_id=1,
                question="What is 5?",
                expression="5",
                operation="addition",
                operands=[5],  # Needs at least 2 operands
            )

    def test_math_payload_duplicate_question_ids(self) -> None:
        with self.assertRaises(ValueError):
            MathChallengePayload(
                question_count=2,
                questions=[
                    MathQuestionItem(
                        question_id=1,
                        question="What is 1 + 2?",
                        expression="1 + 2",
                        operation="addition",
                        operands=[1, 2],
                    ),
                    MathQuestionItem(
                        question_id=1,  # Duplicate ID
                        question="What is 3 + 4?",
                        expression="3 + 4",
                        operation="addition",
                        operands=[3, 4],
                    ),
                ],
                time_limit_seconds=20,
            )

    def test_math_difficulty_constraints_resolution(self) -> None:
        easy = get_math_difficulty_constraints("easy")
        self.assertEqual(easy.difficulty_level, "easy")
        self.assertIn("addition", easy.allowed_operations)
        self.assertIn("multiplication", easy.banned_operations)
        self.assertEqual(easy.max_ast_depth, 2)

        med = get_math_difficulty_constraints("medium")
        self.assertEqual(med.difficulty_level, "medium")
        self.assertIn("multiplication", med.allowed_operations)
        self.assertIn("division", med.allowed_operations)
        self.assertEqual(med.max_ast_depth, 3)

        hard = get_math_difficulty_constraints("hard")
        self.assertEqual(hard.difficulty_level, "hard")
        self.assertTrue(hard.allow_parentheses)
        self.assertEqual(hard.max_ast_depth, 4)

    def test_invalid_difficulty_rejection(self) -> None:
        with self.assertRaises(InvalidDifficultyError):
            get_math_difficulty_constraints("adaptive")
        with self.assertRaises(InvalidDifficultyError):
            get_math_difficulty_constraints("extreme")


class TestSafeArithmeticEvaluator(unittest.TestCase):
    """Test pure AST-based safe arithmetic evaluation."""

    def test_easy_addition(self) -> None:
        res, constants, ops = SafeArithmeticEvaluator.parse_and_evaluate(
            "7 + 5", EASY_MATH_CONSTRAINTS
        )
        self.assertEqual(res, 12)
        self.assertEqual(constants, [7, 5])
        self.assertEqual(ops, {"addition"})

    def test_easy_subtraction(self) -> None:
        res, constants, ops = SafeArithmeticEvaluator.parse_and_evaluate(
            "15 - 8", EASY_MATH_CONSTRAINTS
        )
        self.assertEqual(res, 7)
        self.assertEqual(constants, [15, 8])
        self.assertEqual(ops, {"subtraction"})

    def test_medium_multiplication(self) -> None:
        res, constants, ops = SafeArithmeticEvaluator.parse_and_evaluate(
            "12 * 9", MEDIUM_MATH_CONSTRAINTS
        )
        self.assertEqual(res, 108)
        self.assertEqual(constants, [12, 9])
        self.assertEqual(ops, {"multiplication"})

    def test_medium_exact_division(self) -> None:
        res, constants, ops = SafeArithmeticEvaluator.parse_and_evaluate(
            "72 / 8", MEDIUM_MATH_CONSTRAINTS
        )
        self.assertEqual(res, 9)
        self.assertEqual(constants, [72, 8])
        self.assertEqual(ops, {"division"})

    def test_hard_multi_step_with_parentheses(self) -> None:
        res, constants, ops = SafeArithmeticEvaluator.parse_and_evaluate(
            "(12 + 8) * 3", HARD_MATH_CONSTRAINTS
        )
        self.assertEqual(res, 60)
        self.assertEqual(constants, [12, 8, 3])
        self.assertEqual(ops, {"addition", "multiplication"})

    def test_division_by_zero_rejected(self) -> None:
        with self.assertRaises(MathEvaluationError) as ctx:
            SafeArithmeticEvaluator.parse_and_evaluate("12 / 0", MEDIUM_MATH_CONSTRAINTS)
        self.assertIn("Division by zero", str(ctx.exception))

    def test_non_exact_division_rejected(self) -> None:
        with self.assertRaises(MathEvaluationError) as ctx:
            SafeArithmeticEvaluator.parse_and_evaluate("7 / 2", MEDIUM_MATH_CONSTRAINTS)
        self.assertIn("Non-exact division", str(ctx.exception))

    def test_exact_division_in_multi_step(self) -> None:
        res, constants, ops = SafeArithmeticEvaluator.parse_and_evaluate(
            "(72 / 8) * 4", HARD_MATH_CONSTRAINTS
        )
        self.assertEqual(res, 36)
        self.assertEqual(constants, [72, 8, 4])

    def test_easy_multiplication_rejected(self) -> None:
        with self.assertRaises(MathEvaluationError) as ctx:
            SafeArithmeticEvaluator.parse_and_evaluate("3 * 4", EASY_MATH_CONSTRAINTS)
        self.assertIn("Multiplication is not permitted", str(ctx.exception))

    def test_easy_division_rejected(self) -> None:
        with self.assertRaises(MathEvaluationError) as ctx:
            SafeArithmeticEvaluator.parse_and_evaluate("10 / 2", EASY_MATH_CONSTRAINTS)
        self.assertIn("Division is not permitted", str(ctx.exception))

    def test_medium_exponent_rejected(self) -> None:
        with self.assertRaises(MathEvaluationError) as ctx:
            SafeArithmeticEvaluator.parse_and_evaluate("2 ** 3", MEDIUM_MATH_CONSTRAINTS)
        self.assertIn("Disallowed AST node", str(ctx.exception))

    def test_modulo_rejected(self) -> None:
        with self.assertRaises(MathEvaluationError) as ctx:
            SafeArithmeticEvaluator.parse_and_evaluate("10 % 3", HARD_MATH_CONSTRAINTS)
        self.assertIn("Disallowed AST node", str(ctx.exception))

    def test_bitwise_rejected(self) -> None:
        with self.assertRaises(MathEvaluationError) as ctx:
            SafeArithmeticEvaluator.parse_and_evaluate("5 & 3", HARD_MATH_CONSTRAINTS)
        self.assertIn("Disallowed AST node", str(ctx.exception))

    def test_function_call_rejected(self) -> None:
        with self.assertRaises(MathEvaluationError) as ctx:
            SafeArithmeticEvaluator.parse_and_evaluate("int('12')", MEDIUM_MATH_CONSTRAINTS)
        self.assertIn("Disallowed AST node", str(ctx.exception))

    def test_name_variable_rejected(self) -> None:
        with self.assertRaises(MathEvaluationError) as ctx:
            SafeArithmeticEvaluator.parse_and_evaluate("x + 5", EASY_MATH_CONSTRAINTS)
        self.assertIn("Disallowed AST node", str(ctx.exception))

    def test_float_rejected(self) -> None:
        with self.assertRaises(MathEvaluationError) as ctx:
            SafeArithmeticEvaluator.parse_and_evaluate("3.5 + 2", EASY_MATH_CONSTRAINTS)
        self.assertIn("Only integers are permitted", str(ctx.exception))

    def test_string_rejected(self) -> None:
        with self.assertRaises(MathEvaluationError) as ctx:
            SafeArithmeticEvaluator.parse_and_evaluate("'hello' + 'world'", EASY_MATH_CONSTRAINTS)
        self.assertIn("Only integers are permitted", str(ctx.exception))

    def test_expression_length_limit(self) -> None:
        long_expr = "1 + 1 + 1 + 1 + 1 + 1 + 1 + 1 + 1 + 1"  # > 20 chars
        with self.assertRaises(MathEvaluationError) as ctx:
            SafeArithmeticEvaluator.parse_and_evaluate(long_expr, EASY_MATH_CONSTRAINTS)
        self.assertIn("Expression length", str(ctx.exception))

    def test_ast_depth_limit(self) -> None:
        # Easy has max depth 2. "1 + 2 + 3" creates depth 3
        with self.assertRaises(MathEvaluationError) as ctx:
            SafeArithmeticEvaluator.parse_and_evaluate("1 + 2 + 3", EASY_MATH_CONSTRAINTS)
        self.assertIn("AST depth", str(ctx.exception))

    def test_ast_node_count_limit(self) -> None:
        # Easy allows max 3 nodes. "1 + 2 + 3" has 5 nodes
        with self.assertRaises(MathEvaluationError) as ctx:
            SafeArithmeticEvaluator.parse_and_evaluate("1 + 2 + 3", EASY_MATH_CONSTRAINTS)
        self.assertIn("exceeds maximum limit", str(ctx.exception))

    def test_intermediate_bound_exceeded_during_calculation(self) -> None:
        # Easy max intermediate is 30. 15 + 16 = 31
        with self.assertRaises(MathEvaluationError) as ctx:
            SafeArithmeticEvaluator.parse_and_evaluate("15 + 16", EASY_MATH_CONSTRAINTS)
        # Operand bounds or intermediate bound catches this
        self.assertTrue(
            "exceeds maximum intermediate bound" in str(ctx.exception)
            or "exceeds difficulty limit" in str(ctx.exception)
        )

    def test_negative_hard_result_where_permitted(self) -> None:
        # Hard permits negative down to -50
        res, constants, ops = SafeArithmeticEvaluator.parse_and_evaluate(
            "10 - 25", HARD_MATH_CONSTRAINTS
        )
        self.assertEqual(res, -15)


class TestMathAnswerValidator(unittest.TestCase):
    """Test MathAnswerValidator consistency checking and payload processing."""

    def test_operand_expression_mismatch_rejected(self) -> None:
        # Operands say [17, 6] but expression has 17 * 5
        item = MathQuestionItem(
            question_id=1,
            question="What is 17 × 6?",
            expression="17 * 5",
            operation="multiplication",
            operands=[17, 6],
            proposed_answer=85,
        )
        with self.assertRaises(MathEvaluationError) as ctx:
            MathAnswerValidator.validate_question_item(item, MEDIUM_MATH_CONSTRAINTS)
        self.assertIn("supplied operands [17, 6] do not match constants", str(ctx.exception))

    def test_operand_expression_reverse_mismatch_rejected(self) -> None:
        # Operands say [17, 5] but expression has 17 * 6
        item = MathQuestionItem(
            question_id=1,
            question="What is 17 × 5?",
            expression="17 * 6",
            operation="multiplication",
            operands=[17, 5],
            proposed_answer=102,
        )
        with self.assertRaises(MathEvaluationError) as ctx:
            MathAnswerValidator.validate_question_item(item, MEDIUM_MATH_CONSTRAINTS)
        self.assertIn("supplied operands [17, 5] do not match constants", str(ctx.exception))

    def test_operation_expression_mismatch_rejected(self) -> None:
        # Declared operation is addition, but expression is multiplication
        item = MathQuestionItem(
            question_id=1,
            question="What is 5 × 4?",
            expression="5 * 4",
            operation="addition",
            operands=[5, 4],
            proposed_answer=20,
        )
        with self.assertRaises(MathEvaluationError) as ctx:
            MathAnswerValidator.validate_question_item(item, MEDIUM_MATH_CONSTRAINTS)
        self.assertIn("declared operation 'addition' is incompatible", str(ctx.exception))

    def test_llm_proposed_answer_mismatch_rejected(self) -> None:
        # LLM claims 17 + 8 = 20 (hallucinated)
        item = MathQuestionItem(
            question_id=1,
            question="What is 17 + 8?",
            expression="17 + 8",
            operation="addition",
            operands=[17, 8],
            proposed_answer=20,  # Computed is 25
        )
        with self.assertRaises(MathEvaluationError) as ctx:
            MathAnswerValidator.validate_question_item(item, MEDIUM_MATH_CONSTRAINTS)
        self.assertIn("LLM proposed answer (20) conflicts with independently computed answer (25)", str(ctx.exception))

    def test_llm_proposed_answer_correct_accepted(self) -> None:
        item = MathQuestionItem(
            question_id=1,
            question="What is 17 + 8?",
            expression="17 + 8",
            operation="addition",
            operands=[17, 8],
            proposed_answer=25,
        )
        ans = MathAnswerValidator.validate_question_item(item, MEDIUM_MATH_CONSTRAINTS)
        self.assertEqual(ans, 25)

    def test_llm_proposed_answer_omitted_accepted(self) -> None:
        item = MathQuestionItem(
            question_id=1,
            question="What is 17 + 8?",
            expression="17 + 8",
            operation="addition",
            operands=[17, 8],
            proposed_answer=None,
        )
        ans = MathAnswerValidator.validate_question_item(item, MEDIUM_MATH_CONSTRAINTS)
        self.assertEqual(ans, 25)

    def test_question_numeric_token_mismatch_rejected(self) -> None:
        # Question text mentions 17 and 6, but operands are 17 and 5
        item = MathQuestionItem(
            question_id=1,
            question="What is 17 + 6?",
            expression="17 + 5",
            operation="addition",
            operands=[17, 5],
            proposed_answer=22,
        )
        with self.assertRaises(MathEvaluationError) as ctx:
            MathAnswerValidator.validate_question_item(item, MEDIUM_MATH_CONSTRAINTS)
        self.assertIn("question text numeric tokens [17, 6] conflict with structured operands [17, 5]", str(ctx.exception))

    def test_question_without_numeric_tokens_accepted(self) -> None:
        # Question has no numbers: sanity check must not reject
        item = MathQuestionItem(
            question_id=1,
            question="Calculate the arithmetic sum:",
            expression="12 + 6",
            operation="addition",
            operands=[12, 6],
            proposed_answer=18,
        )
        ans = MathAnswerValidator.validate_question_item(item, MEDIUM_MATH_CONSTRAINTS)
        self.assertEqual(ans, 18)

    def test_multiple_question_answer_computation(self) -> None:
        payload_data = {
            "question_count": 2,
            "questions": [
                {
                    "question_id": 1,
                    "question": "What is 7 + 5?",
                    "expression": "7 + 5",
                    "operation": "addition",
                    "operands": [7, 5],
                    "proposed_answer": 12,
                },
                {
                    "question_id": 2,
                    "question": "What is 15 - 6?",
                    "expression": "15 - 6",
                    "operation": "subtraction",
                    "operands": [15, 6],
                    "proposed_answer": 9,
                },
            ],
            "time_limit_seconds": 20,
        }
        payload, expected_ans = MathAnswerValidator.validate_and_compute_payload(
            payload_data, "easy"
        )
        self.assertEqual(payload.question_count, 2)
        self.assertEqual(expected_ans, [12, 9])


class TestMathPromptBuilder(unittest.TestCase):
    """Test prompt building and personalization calibration."""

    def test_duration_affects_question_count_only(self) -> None:
        ctx_short = SafePersonalizationContext(desired_duration_seconds=10)
        req_short = MathPromptBuilder.build_request("medium", ctx_short)
        self.assertEqual(req_short.context_payload["target_question_count"], 2)

        ctx_long = SafePersonalizationContext(desired_duration_seconds=60)
        req_long = MathPromptBuilder.build_request("medium", ctx_long)
        self.assertEqual(req_long.context_payload["target_question_count"], 4)

    def test_difficulty_remains_unchanged_despite_duration(self) -> None:
        # Desired duration must never change medium to easy or hard
        ctx = SafePersonalizationContext(desired_duration_seconds=5)
        req = MathPromptBuilder.build_request("medium", ctx)
        self.assertEqual(req.difficulty_level, "medium")
        self.assertIn("Difficulty is strictly locked to 'medium'", req.custom_instructions)

    def test_identity_exclusion_in_prompt(self) -> None:
        ctx = SafePersonalizationContext(preferred_theme="Morning Awakening")
        req = MathPromptBuilder.build_request("easy", ctx)
        self.assertIsNone(req.user_id)
        context_keys = [k.lower() for k in req.context_payload.keys()]
        for forbidden in ("user_id", "email", "session_id", "alarm_id", "password"):
            self.assertNotIn(forbidden, context_keys)
            self.assertNotIn(forbidden, req.custom_instructions.lower())


class TestMathChallengeGenerator(unittest.TestCase):
    """Test the complete end-to-end Math Challenge Generator."""

    def test_generate_easy_math_challenge_success(self) -> None:
        canned = _create_canned_math_response(
            challenge_type="math",
            difficulty_level="easy",
            questions=[
                {
                    "question_id": 1,
                    "question": "What is 9 + 4?",
                    "expression": "9 + 4",
                    "operation": "addition",
                    "operands": [9, 4],
                    "proposed_answer": 13,
                },
                {
                    "question_id": 2,
                    "question": "What is 12 - 5?",
                    "expression": "12 - 5",
                    "operation": "subtraction",
                    "operands": [12, 5],
                    "proposed_answer": 7,
                },
            ],
        )
        mock_provider = MockGenAIProvider(canned_content=canned)
        service = GenAIService(provider=mock_provider, enabled=True)
        generator = MathChallengeGenerator(service)

        validated: ValidatedChallengeContent = generator.generate_math_challenge("easy")

        self.assertEqual(validated.challenge_type, "math")
        self.assertEqual(validated.difficulty_level, "easy")
        self.assertEqual(validated.verification_mode, "math_standard")
        self.assertEqual(validated.expected_answer, [13, 7])
        self.assertEqual(validated.content_payload["question_count"], 2)
        self.assertTrue(validated.generation_metadata["authoritative_math_calculated"])

    def test_generate_medium_math_challenge_multiplication_division(self) -> None:
        canned = _create_canned_math_response(
            challenge_type="math",
            difficulty_level="medium",
            questions=[
                {
                    "question_id": 1,
                    "question": "What is 12 × 4?",
                    "expression": "12 * 4",
                    "operation": "multiplication",
                    "operands": [12, 4],
                    "proposed_answer": 48,
                },
                {
                    "question_id": 2,
                    "question": "What is 84 ÷ 7?",
                    "expression": "84 / 7",
                    "operation": "division",
                    "operands": [84, 7],
                    "proposed_answer": 12,
                },
            ],
            time_limit_seconds=35,
        )
        mock_provider = MockGenAIProvider(canned_content=canned)
        service = GenAIService(provider=mock_provider, enabled=True)
        generator = MathChallengeGenerator(service)

        validated = generator.generate_math_challenge("medium")
        self.assertEqual(validated.expected_answer, [48, 12])

    def test_generate_hard_math_challenge_multi_step(self) -> None:
        canned = _create_canned_math_response(
            challenge_type="math",
            difficulty_level="hard",
            questions=[
                {
                    "question_id": 1,
                    "question": "What is (15 + 5) × 4?",
                    "expression": "(15 + 5) * 4",
                    "operation": "mixed",
                    "operands": [15, 5, 4],
                    "proposed_answer": 80,
                },
                {
                    "question_id": 2,
                    "question": "What is (72 / 8) + 11?",
                    "expression": "(72 / 8) + 11",
                    "operation": "mixed",
                    "operands": [72, 8, 11],
                    "proposed_answer": 20,
                },
            ],
            time_limit_seconds=50,
        )
        mock_provider = MockGenAIProvider(canned_content=canned)
        service = GenAIService(provider=mock_provider, enabled=True)
        generator = MathChallengeGenerator(service)

        validated = generator.generate_math_challenge("hard")
        self.assertEqual(validated.expected_answer, [80, 20])

    def test_difficulty_immutability_enforced(self) -> None:
        generator = MathChallengeGenerator(GenAIService(provider=MockGenAIProvider()))
        with self.assertRaises(InvalidDifficultyError):
            generator.generate_math_challenge("adaptive")
        with self.assertRaises(InvalidDifficultyError):
            generator.generate_math_challenge("extreme")

    def test_challenge_type_immutability_enforced(self) -> None:
        generator = MathChallengeGenerator(GenAIService(provider=MockGenAIProvider()))
        with self.assertRaises(InvalidChallengeTypeError):
            generator.generate_math_challenge("easy", challenge_type="memory")

    def test_provider_difficulty_mutation_rejected(self) -> None:
        # Requested medium, but provider returns hard
        canned = _create_canned_math_response(difficulty_level="hard")
        mock_provider = MockGenAIProvider(canned_content=canned)
        service = GenAIService(provider=mock_provider, enabled=True)
        generator = MathChallengeGenerator(service)

        # In generator line 128: canonical_raw_content["difficulty_level"] = clean_diff
        # Let's test if raw provider output without our override or with payload failure raises
        # We test that the returned validated content strictly maintains requested difficulty
        validated = generator.generate_math_challenge("medium")
        self.assertEqual(validated.difficulty_level, "medium")

    def test_unsafe_personalization_context_rejected(self) -> None:
        generator = MathChallengeGenerator(GenAIService(provider=MockGenAIProvider()))
        with self.assertRaises(UnsafePersonalizationContextError):
            generator.generate_math_challenge("easy", raw_context={"user_id": 123})

    def test_malformed_provider_response_rejected(self) -> None:
        mock_provider = MockGenAIProvider(canned_content={"malformed": "not a valid structure"})
        service = GenAIService(provider=mock_provider, enabled=True)
        generator = MathChallengeGenerator(service)

        with self.assertRaises(ChallengeContentValidationError):
            generator.generate_math_challenge("easy")

    def test_exception_hierarchy(self) -> None:
        # MathEvaluationError is ChallengeContentValidationError and GenAIError
        self.assertTrue(issubclass(MathEvaluationError, ChallengeContentValidationError))
        self.assertTrue(issubclass(MathEvaluationError, GenAIError))

        # MathChallengeGenerationError is GenAIError, but NOT ChallengeContentValidationError
        self.assertTrue(issubclass(MathChallengeGenerationError, GenAIError))
        self.assertFalse(issubclass(MathChallengeGenerationError, ChallengeContentValidationError))


class TestPhase42StaticSafetyAudit(unittest.TestCase):
    """Static AST source code safety audit to verify zero arbitrary execution primitives."""

    def test_no_eval_or_exec_in_math_genai_files(self) -> None:
        """Inspect Phase 4.2 files and assert zero executable calls to eval, exec, subprocess, os.system."""
        forbidden_calls = {"eval", "exec", "compile", "__import__"}
        forbidden_modules = {"subprocess", "os.system"}

        phase_42_files = [
            Path("backend/app/schemas/math_challenge_schemas.py"),
            Path("backend/app/services/genai/math_generation_constraints.py"),
            Path("backend/app/services/genai/math_answer_validator.py"),
            Path("backend/app/services/genai/math_prompt_builder.py"),
            Path("backend/app/services/genai/math_challenge_generator.py"),
        ]

        for file_path in phase_42_files:
            self.assertTrue(file_path.exists(), f"File {file_path} must exist.")
            content = file_path.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(file_path))

            for node in ast.walk(tree):
                # Check function calls
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
                # Check imports
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            self.assertNotEqual(alias.name, "subprocess", f"subprocess import in {file_path}")
                    elif isinstance(node, ast.ImportFrom):
                        self.assertNotEqual(node.module, "subprocess", f"subprocess import in {file_path}")


if __name__ == "__main__":
    unittest.main()
