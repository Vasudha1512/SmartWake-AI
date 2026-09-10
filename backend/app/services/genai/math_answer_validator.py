"""Deterministic Math Answer Validator and Safe Arithmetic Evaluator for SmartWake AI (Phase 4.2).

CRITICAL TRUST BOUNDARY:
Never treats GenAI-provided answers as authoritative. Independently parses, validates,
and calculates mathematical expressions using a strict, pure AST visitor without eval() or exec().
Enforces operand/expression consistency, strict numeric safety bounds, exact integer division,
and question text sanity checks.
"""
import ast
import re
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from backend.app.core.exceptions import MathEvaluationError
from backend.app.schemas.math_challenge_schemas import (
    MathChallengePayload,
    MathQuestionItem,
)
from backend.app.services.genai.math_generation_constraints import (
    MathGenerationConstraints,
    get_math_difficulty_constraints,
)

# Whitelisted AST node classes permitted during expression parsing
ALLOWED_AST_NODES: Set[type] = {
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Constant,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.UAdd,
    ast.USub,
}

# Explicitly banned AST node classes
DISALLOWED_AST_NODES: Set[type] = {
    ast.Call,
    ast.Name,
    ast.Attribute,
    ast.Pow,
    ast.Mod,
    ast.BitOr,
    ast.BitAnd,
    ast.BitXor,
    ast.LShift,
    ast.RShift,
    ast.Invert,
    ast.Compare,
    ast.BoolOp,
    ast.Lambda,
    ast.List,
    ast.Dict,
    ast.Set,
    ast.Tuple,
    ast.Subscript,
    ast.Slice,
    ast.IfExp,
    ast.comprehension,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
    ast.NamedExpr,
}


class SafeArithmeticEvaluator:
    """Pure in-memory, AST-based safe arithmetic evaluator.

    ABSOLUTELY FORBIDDEN: eval(), exec(), compile(), dynamic imports, shell commands.
    """

    @classmethod
    def get_ast_depth(cls, node: ast.AST) -> int:
        """Calculate the maximum depth of an AST tree (measured from expression body)."""
        if isinstance(node, ast.Expression):
            return cls.get_ast_depth(node.body)
        if not isinstance(node, ast.AST):
            return 0
        children = [c for c in ast.iter_child_nodes(node) if isinstance(c, (ast.BinOp, ast.UnaryOp, ast.Constant))]
        if not children:
            return 1
        return 1 + max(cls.get_ast_depth(child) for child in children)

    @classmethod
    def count_ast_nodes(cls, node: ast.AST) -> int:
        """Count semantic arithmetic evaluation nodes (BinOp, UnaryOp, Constant) in expression."""
        if isinstance(node, ast.Expression):
            node = node.body
        return sum(1 for sub in ast.walk(node) if isinstance(sub, (ast.BinOp, ast.UnaryOp, ast.Constant)))

    @classmethod
    def extract_constants(cls, node: ast.AST) -> List[int]:
        """Extract integer constants from the AST in infix (left-to-right) traversal order."""
        constants: List[int] = []
        if isinstance(node, ast.Expression):
            return cls.extract_constants(node.body)
        elif isinstance(node, ast.BinOp):
            constants.extend(cls.extract_constants(node.left))
            constants.extend(cls.extract_constants(node.right))
        elif isinstance(node, ast.UnaryOp):
            if (
                isinstance(node.op, ast.USub)
                and isinstance(node.operand, ast.Constant)
                and isinstance(node.operand.value, int)
                and not isinstance(node.operand.value, bool)
            ):
                constants.append(-node.operand.value)
            elif (
                isinstance(node.op, ast.UAdd)
                and isinstance(node.operand, ast.Constant)
                and isinstance(node.operand.value, int)
                and not isinstance(node.operand.value, bool)
            ):
                constants.append(node.operand.value)
            else:
                constants.extend(cls.extract_constants(node.operand))
        elif isinstance(node, ast.Constant):
            if isinstance(node.value, int) and not isinstance(node.value, bool):
                constants.append(node.value)
        return constants

    @classmethod
    def detect_used_operations(cls, node: ast.AST) -> Set[str]:
        """Inspect AST binary operators and return canonical operation names."""
        ops: Set[str] = set()
        for subnode in ast.walk(node):
            if isinstance(subnode, ast.Add):
                ops.add("addition")
            elif isinstance(subnode, ast.Sub):
                ops.add("subtraction")
            elif isinstance(subnode, ast.Mult):
                ops.add("multiplication")
            elif isinstance(subnode, (ast.Div, ast.FloorDiv)):
                ops.add("division")
            elif isinstance(subnode, ast.Pow):
                ops.add("exponent")
            elif isinstance(subnode, ast.Mod):
                ops.add("modulo")
            elif isinstance(subnode, (ast.BitOr, ast.BitAnd, ast.BitXor, ast.LShift, ast.RShift)):
                ops.add("bitwise")
        return ops

    @classmethod
    def evaluate_node(
        cls, node: ast.AST, constraints: MathGenerationConstraints
    ) -> int:
        """Step-by-step recursive evaluation enforcing intermediate limits and exact division."""
        if isinstance(node, ast.Expression):
            return cls.evaluate_node(node.body, constraints)

        if isinstance(node, ast.Constant):
            if not isinstance(node.value, int) or isinstance(node.value, bool):
                raise MathEvaluationError(
                    f"Constant of type '{type(node.value).__name__}' is forbidden. Only integers are permitted."
                )
            if abs(node.value) > constraints.max_operand_abs:
                raise MathEvaluationError(
                    f"Operand absolute value {abs(node.value)} exceeds difficulty limit of {constraints.max_operand_abs}."
                )
            return node.value

        if isinstance(node, ast.UnaryOp):
            operand_val = cls.evaluate_node(node.operand, constraints)
            if isinstance(node.op, ast.UAdd):
                res = +operand_val
            elif isinstance(node.op, ast.USub):
                res = -operand_val
            else:
                raise MathEvaluationError(f"Disallowed unary operator '{type(node.op).__name__}'.")

            if abs(res) > constraints.max_intermediate_abs:
                raise MathEvaluationError(
                    f"Unary intermediate result {res} exceeds maximum intermediate bound of {constraints.max_intermediate_abs}."
                )
            return res

        if isinstance(node, ast.BinOp):
            left_val = cls.evaluate_node(node.left, constraints)
            right_val = cls.evaluate_node(node.right, constraints)

            if isinstance(node.op, ast.Add):
                if "addition" in constraints.banned_operations or "addition" not in constraints.allowed_operations:
                    raise MathEvaluationError(f"Addition is not permitted for difficulty '{constraints.difficulty_level}'.")
                res = left_val + right_val
            elif isinstance(node.op, ast.Sub):
                if "subtraction" in constraints.banned_operations or "subtraction" not in constraints.allowed_operations:
                    raise MathEvaluationError(f"Subtraction is not permitted for difficulty '{constraints.difficulty_level}'.")
                res = left_val - right_val
            elif isinstance(node.op, ast.Mult):
                if "multiplication" in constraints.banned_operations or "multiplication" not in constraints.allowed_operations:
                    raise MathEvaluationError(f"Multiplication is not permitted for difficulty '{constraints.difficulty_level}'.")
                res = left_val * right_val
            elif isinstance(node.op, (ast.Div, ast.FloorDiv)):
                if "division" in constraints.banned_operations or "division" not in constraints.allowed_operations:
                    raise MathEvaluationError(f"Division is not permitted for difficulty '{constraints.difficulty_level}'.")
                if right_val == 0:
                    raise MathEvaluationError("Division by zero is strictly prohibited.")
                if constraints.exact_division_required and (left_val % right_val != 0):
                    raise MathEvaluationError(
                        f"Non-exact division: {left_val} / {right_val} leaves remainder {left_val % right_val}. "
                        "Only exact integer division is permitted."
                    )
                res = left_val // right_val
            else:
                raise MathEvaluationError(f"Disallowed binary operator '{type(node.op).__name__}'.")

            # Enforce intermediate result bound immediately
            if abs(res) > constraints.max_intermediate_abs:
                raise MathEvaluationError(
                    f"Intermediate arithmetic result {res} exceeds maximum intermediate bound of {constraints.max_intermediate_abs}."
                )
            return res

        raise MathEvaluationError(f"Disallowed AST node type '{type(node).__name__}'.")

    @classmethod
    def parse_and_evaluate(
        cls, expression_str: str, constraints: MathGenerationConstraints
    ) -> Tuple[int, List[int], Set[str]]:
        """Safely parse and evaluate mathematical expression string.

        Returns:
            Tuple[int, List[int], Set[str]]: (computed_result, expression_constants, used_operations)
        """
        clean_expr = expression_str.strip() if isinstance(expression_str, str) else ""
        if not clean_expr:
            raise MathEvaluationError("Expression string cannot be empty.")

        if len(clean_expr) > constraints.max_expression_length:
            raise MathEvaluationError(
                f"Expression length ({len(clean_expr)}) exceeds maximum allowed ({constraints.max_expression_length} chars)."
            )

        # Disallow dangerous characters or keywords before parsing
        if any(keyword in clean_expr for keyword in ("import", "eval", "exec", "__", "lambda", "def")):
            raise MathEvaluationError("Expression contains forbidden keywords.")

        try:
            tree = ast.parse(clean_expr, mode="eval")
        except SyntaxError as exc:
            raise MathEvaluationError(f"Expression syntax error in '{clean_expr}': {exc}") from exc

        # Enforce strict node whitelist and valid constant types first
        for subnode in ast.walk(tree):
            subnode_type = type(subnode)
            if subnode_type in DISALLOWED_AST_NODES:
                raise MathEvaluationError(
                    f"Disallowed AST node '{subnode_type.__name__}' detected. Arbitrary execution is strictly prevented."
                )
            if subnode_type not in ALLOWED_AST_NODES:
                raise MathEvaluationError(
                    f"Unsupported AST node '{subnode_type.__name__}' detected in mathematical expression."
                )
            if isinstance(subnode, ast.Constant):
                if not isinstance(subnode.value, int) or isinstance(subnode.value, bool):
                    raise MathEvaluationError(
                        f"Constant of type '{type(subnode.value).__name__}' is forbidden. Only integers are permitted."
                    )

        # Check depth and node count limits
        ast_depth = cls.get_ast_depth(tree.body)
        if ast_depth > constraints.max_ast_depth:
            raise MathEvaluationError(
                f"AST depth ({ast_depth}) exceeds maximum limit ({constraints.max_ast_depth}) for '{constraints.difficulty_level}'."
            )

        node_count = cls.count_ast_nodes(tree.body)
        if node_count > constraints.max_ast_node_count:
            raise MathEvaluationError(
                f"AST node count ({node_count}) exceeds maximum limit ({constraints.max_ast_node_count}) for '{constraints.difficulty_level}'."
            )

        # Extract constants in expression order
        constants = cls.extract_constants(tree)

        # Detect used operators
        used_ops = cls.detect_used_operations(tree)

        # Evaluate safely step by step
        result = cls.evaluate_node(tree, constraints)

        return result, constants, used_ops


class MathAnswerValidator:
    """Authoritative mathematical validation engine for AI-generated math challenges."""

    @classmethod
    def validate_question_item(
        cls,
        question_item: MathQuestionItem,
        constraints: MathGenerationConstraints,
    ) -> int:
        """Independently validate a single MathQuestionItem and compute its authoritative answer.

        Sequential validation steps:
        1. Validate supplied operands (count, type, bounds).
        2. Parse expression with restricted AST (no eval/exec, depth/node limits).
        3. Extract expression constants.
        4. Compare expression constants with supplied operands (rejects mismatch).
        5. Validate declared operation against AST operators and tier constraints.
        6. Safely compute result enforcing intermediate bounds and exact division.
        7. Validate final result bounds.
        8. Perform question text consistency sanity check (if numeric tokens present).
        9. Validate LLM proposed_answer if provided (rejects conflict).

        Args:
            question_item: Structured question item from provider.
            constraints: Difficulty-specific mathematical constraints.

        Returns:
            int: The authoritative independently computed answer.

        Raises:
            MathEvaluationError: If any validation or consistency check fails.
        """
        # Step 1: Validate supplied operands
        supplied_operands = question_item.operands
        if not supplied_operands or len(supplied_operands) < 2:
            raise MathEvaluationError(
                f"Question {question_item.question_id}: operands must contain at least 2 integer values."
            )

        for idx, op in enumerate(supplied_operands):
            if not isinstance(op, int) or isinstance(op, bool):
                raise MathEvaluationError(
                    f"Question {question_item.question_id}: operands[{idx}] must be a pure integer, got {type(op).__name__}."
                )
            if abs(op) > constraints.max_operand_abs:
                raise MathEvaluationError(
                    f"Question {question_item.question_id}: operand {op} absolute value exceeds maximum "
                    f"limit of {constraints.max_operand_abs} for difficulty '{constraints.difficulty_level}'."
                )

        # Step 2 & 3 & 6: Parse expression, extract constants, evaluate safely
        computed_result, expr_constants, used_ops = SafeArithmeticEvaluator.parse_and_evaluate(
            question_item.expression, constraints
        )

        # Step 4: Compare expression constants with supplied operands (strict consistency)
        if expr_constants != supplied_operands:
            raise MathEvaluationError(
                f"Question {question_item.question_id}: supplied operands {supplied_operands} "
                f"do not match constants in expression '{question_item.expression}' {expr_constants}."
            )

        # Step 5: Validate declared operation
        decl_op = question_item.operation.strip().lower()

        # Check banned operations
        for op_name in used_ops:
            if op_name in constraints.banned_operations or op_name not in constraints.allowed_operations:
                raise MathEvaluationError(
                    f"Question {question_item.question_id}: operation '{op_name}' is not permitted "
                    f"for difficulty '{constraints.difficulty_level}'."
                )

        # Check compatibility between declared operation and actual operators
        if decl_op == "addition" and (used_ops - {"addition"}):
            raise MathEvaluationError(
                f"Question {question_item.question_id}: declared operation 'addition' is incompatible with expression operators {used_ops}."
            )
        elif decl_op == "subtraction" and (used_ops - {"subtraction"}):
            raise MathEvaluationError(
                f"Question {question_item.question_id}: declared operation 'subtraction' is incompatible with expression operators {used_ops}."
            )
        elif decl_op == "multiplication" and (used_ops - {"multiplication"}):
            raise MathEvaluationError(
                f"Question {question_item.question_id}: declared operation 'multiplication' is incompatible with expression operators {used_ops}."
            )
        elif decl_op == "division" and (used_ops - {"division"}):
            raise MathEvaluationError(
                f"Question {question_item.question_id}: declared operation 'division' is incompatible with expression operators {used_ops}."
            )

        # Step 7: Final result validation
        if not isinstance(computed_result, int) or isinstance(computed_result, bool):
            raise MathEvaluationError(
                f"Question {question_item.question_id}: final computed result must be an integer, got {type(computed_result).__name__}."
            )

        if abs(computed_result) > constraints.max_final_abs:
            raise MathEvaluationError(
                f"Question {question_item.question_id}: final result absolute value {abs(computed_result)} "
                f"exceeds difficulty maximum of {constraints.max_final_abs}."
            )

        if computed_result < constraints.min_final_result or computed_result > constraints.max_final_result:
            raise MathEvaluationError(
                f"Question {question_item.question_id}: final result {computed_result} is outside permitted range "
                f"[{constraints.min_final_result}, {constraints.max_final_result}] for difficulty '{constraints.difficulty_level}'."
            )

        # Step 8: Question text consistency sanity check
        question_text = question_item.question.strip()
        numeric_tokens = re.findall(r"\b\d+\b", question_text)
        if numeric_tokens:
            token_ints = [int(tok) for tok in numeric_tokens]
            # Compare extracted numbers against supplied operands
            # If the numbers extracted from question conflict with operands, reject
            if token_ints != supplied_operands and sorted(token_ints) != sorted(supplied_operands):
                raise MathEvaluationError(
                    f"Question {question_item.question_id}: question text numeric tokens {token_ints} "
                    f"conflict with structured operands {supplied_operands}."
                )

        # Step 9: Validate LLM proposed_answer if supplied (NEVER trusted)
        if question_item.proposed_answer is not None:
            if question_item.proposed_answer != computed_result:
                raise MathEvaluationError(
                    f"Question {question_item.question_id}: LLM proposed answer ({question_item.proposed_answer}) "
                    f"conflicts with independently computed answer ({computed_result})."
                )

        return computed_result

    @classmethod
    def validate_and_compute_payload(
        cls,
        payload_data: Union[MathChallengePayload, Dict[str, Any]],
        difficulty_level: str,
    ) -> Tuple[MathChallengePayload, Union[int, List[int]]]:
        """Validate entire math challenge payload and compute authoritative expected_answer(s).

        Args:
            payload_data: MathChallengePayload model or dictionary.
            difficulty_level: Concrete difficulty level ('easy', 'medium', 'hard').

        Returns:
            Tuple[MathChallengePayload, Union[int, List[int]]]:
                - Validated MathChallengePayload model
                - Authoritative expected_answer: int if single question, List[int] if multi-question.

        Raises:
            MathEvaluationError: If payload or any individual question violates validation rules.
        """
        constraints = get_math_difficulty_constraints(difficulty_level)

        if isinstance(payload_data, dict):
            try:
                payload = MathChallengePayload(**payload_data)
            except Exception as exc:
                raise MathEvaluationError(f"Malformed math challenge payload: {exc}") from exc
        elif isinstance(payload_data, MathChallengePayload):
            payload = payload_data
        else:
            raise MathEvaluationError(
                f"Math payload must be a dictionary or MathChallengePayload, got {type(payload_data).__name__}."
            )

        # Verify question_count matches questions length
        if payload.question_count != len(payload.questions):
            raise MathEvaluationError(
                f"Payload question_count ({payload.question_count}) does not match number of questions ({len(payload.questions)})."
            )

        # Enforce question count bounds for difficulty
        if payload.question_count < constraints.min_question_count or payload.question_count > constraints.max_question_count:
            raise MathEvaluationError(
                f"Question count ({payload.question_count}) is outside permitted range "
                f"[{constraints.min_question_count}, {constraints.max_question_count}] for difficulty '{constraints.difficulty_level}'."
            )

        # Validate each question independently
        computed_answers: List[int] = []
        for q_item in payload.questions:
            ans = cls.validate_question_item(q_item, constraints)
            computed_answers.append(ans)

        # Structure expected_answer: list of ints for multi-question, single int for 1 question
        expected_answer: Union[int, List[int]]
        if len(computed_answers) == 1:
            expected_answer = computed_answers[0]
        else:
            expected_answer = computed_answers

        return payload, expected_answer
