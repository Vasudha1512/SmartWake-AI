"""Deterministic Memory Answer Validator for SmartWake AI (Phase 4.3).

CRITICAL TRUST BOUNDARY:
Never treats GenAI-provided answers as authoritative. Independently validates memory structure,
enforces targeted non-numeric item rules, ensures deterministic coordinate bounds (zero clamping),
validates dynamic spatial path continuity, and derives authoritative expected answers.
"""
import re
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from backend.app.core.exceptions import MemoryEvaluationError
from backend.app.schemas.memory_challenge_schemas import (
    MemoryChallengePayload,
    VALID_RECALL_MODES,
)
from backend.app.services.genai.memory_generation_constraints import (
    FORBIDDEN_NUMERIC_MEMORY_PHRASES,
    MemoryGenerationConstraints,
    get_memory_difficulty_constraints,
)

# Regex matching numeric digit strings or arithmetic expressions in memory items
NUMERIC_ITEM_REGEX = re.compile(r"^\s*-?\d+(\.\d+)?\s*$")
ARITHMETIC_EXPR_REGEX = re.compile(r"[0-9]+[\s]*[\+\-\*\/\%][\s]*[0-9]+")


class MemoryAnswerValidator:
    """Pure in-memory validation and answer derivation engine for memory challenges."""

    @classmethod
    def scan_for_forbidden_numeric_concepts(cls, text: str) -> None:
        """Scan text for context-aware forbidden numeric memory phrases."""
        if not text or not isinstance(text, str):
            return
        lower_text = text.lower()
        # Check longer phrases first (e.g. 'pin code' before 'pin')
        for phrase in sorted(FORBIDDEN_NUMERIC_MEMORY_PHRASES, key=len, reverse=True):
            if len(phrase) <= 4 and " " not in phrase and "_" not in phrase:
                if re.search(rf"\b{re.escape(phrase)}\b", lower_text):
                    raise MemoryEvaluationError(
                        f"Forbidden numeric memory concept '{phrase}' detected in challenge content. "
                        "Memory challenges strictly forbid number guessing, OTPs, and PIN sequences."
                    )
            elif phrase in lower_text:
                raise MemoryEvaluationError(
                    f"Forbidden numeric memory concept '{phrase}' detected in challenge content. "
                    "Memory challenges strictly forbid number guessing, OTPs, and PIN sequences."
                )

    @classmethod
    def validate_non_numeric_items(cls, items: Optional[List[str]], field_name: str) -> None:
        """Enforce strict non-numeric rule on user-memory items (Correction 1 & 4)."""
        if items is None:
            return
        for idx, item in enumerate(items):
            # Check for pure numeric digit strings (e.g. "42", "3819")
            if NUMERIC_ITEM_REGEX.match(item):
                raise MemoryEvaluationError(
                    f"Forbidden numeric memory item '{item}' detected in {field_name}[{idx}]. "
                    "Memory challenge items must be non-numeric (colors, shapes, symbols, or objects)."
                )
            # Check for arithmetic expressions (e.g. "5 + 4")
            if ARITHMETIC_EXPR_REGEX.search(item):
                raise MemoryEvaluationError(
                    f"Forbidden arithmetic expression '{item}' detected in {field_name}[{idx}]."
                )
            # Scan for forbidden concepts inside item text
            cls.scan_for_forbidden_numeric_concepts(item)

    @classmethod
    def validate_coordinate(
        cls, coord: List[int], matrix_size: int, field_name: str, idx: int
    ) -> Tuple[int, int]:
        """Validate a single grid coordinate without clamping (Correction 2)."""
        if not isinstance(coord, list) or len(coord) != 2:
            raise MemoryEvaluationError(
                f"{field_name}[{idx}] must be a 2-element [row, col] list, got {coord}."
            )
        r, c = coord
        if not isinstance(r, int) or isinstance(r, bool) or not isinstance(c, int) or isinstance(c, bool):
            raise MemoryEvaluationError(
                f"{field_name}[{idx}] values must be pure integers, got [{type(r).__name__}, {type(c).__name__}]."
            )
        # Strictly reject out-of-bounds coordinates (ZERO CLAMPING)
        if r < 0 or r >= matrix_size or c < 0 or c >= matrix_size:
            raise MemoryEvaluationError(
                f"Coordinate [{r}, {c}] in {field_name}[{idx}] is out of bounds for matrix_size {matrix_size} "
                f"(valid range is [0, {matrix_size - 1}])."
            )
        return r, c

    @classmethod
    def validate_path_continuity(
        cls, path_steps: List[List[int]], matrix_size: int
    ) -> None:
        """Validate path steps are strictly adjacent and non-repeating (Correction 3)."""
        if len(path_steps) < 2:
            raise MemoryEvaluationError("dynamic_spatial_path requires at least 2 steps.")

        visited: Set[Tuple[int, int]] = set()

        for i in range(len(path_steps)):
            r, c = cls.validate_coordinate(path_steps[i], matrix_size, "path_steps", i)
            cell = (r, c)
            if cell in visited:
                raise MemoryEvaluationError(
                    f"Duplicate step [{r}, {c}] detected at path_steps[{i}]. Path steps must be distinct."
                )
            visited.add(cell)

            if i > 0:
                prev_r, prev_c = path_steps[i - 1]
                # Chebyshev distance = max(|r2 - r1|, |c2 - c1|)
                dist = max(abs(r - prev_r), abs(c - prev_c))
                if dist == 0:
                    raise MemoryEvaluationError(
                        f"Stationary step detected at path_steps[{i}]: [{r}, {c}] is identical to previous step."
                    )
                if dist > 1:
                    raise MemoryEvaluationError(
                        f"Non-adjacent step jump detected from [{prev_r}, {prev_c}] to [{r}, {c}] "
                        f"(Chebyshev distance is {dist}; must be exactly 1)."
                    )

    @classmethod
    def validate_and_derive_answer(
        cls,
        payload: MemoryChallengePayload,
        difficulty_level: str,
    ) -> Tuple[MemoryChallengePayload, Any]:
        """Validate memory challenge payload and derive authoritative expected_answer.

        Authoritative execution pipeline (Correction 8):
        1. Validate supported recall mode against concrete difficulty constraints.
        2. Validate targeted non-numeric items.
        3. Validate mode-specific bounds (sequence length, matrix size, coordinates).
        4. Validate path continuity for dynamic_spatial_path.
        5. Derive authoritative expected_answer deterministically.
        6. Validate optional proposed_answer consistency.

        Args:
            payload: Validated MemoryChallengePayload model.
            difficulty_level: Authoritative concrete difficulty ('easy', 'medium', 'hard').

        Returns:
            Tuple[MemoryChallengePayload, Any]: Validated payload and authoritative expected_answer.

        Raises:
            MemoryEvaluationError: If memory structure, bounds, items, or continuity checks fail.
        """
        constraints = get_memory_difficulty_constraints(difficulty_level)
        mode = payload.recall_mode

        # 1. Mode check against tier
        if mode not in constraints.allowed_recall_modes:
            raise MemoryEvaluationError(
                f"Recall mode '{mode}' is not permitted for difficulty '{constraints.difficulty_level}'. "
                f"Allowed modes: {sorted(list(constraints.allowed_recall_modes))}."
            )

        # 2. Targeted non-numeric items scan
        cls.validate_non_numeric_items(payload.display_sequence, "display_sequence")
        cls.validate_non_numeric_items(payload.palette, "palette")

        authoritative_answer: Any

        # 3. Mode-specific structural and bound checks
        if mode in ("visual_sequence", "symbol_chronological_order"):
            if payload.matrix_size is not None or payload.grid_dimension is not None or payload.highlighted_cells is not None or payload.path_steps is not None:
                raise MemoryEvaluationError(
                    f"Malformed field combination: '{mode}' must not contain spatial/grid fields (matrix_size, grid_dimension, highlighted_cells, path_steps)."
                )
            if not payload.display_sequence:
                raise MemoryEvaluationError(
                    f"'{mode}' requires non-empty 'display_sequence'."
                )
            if payload.sequence_length is not None and payload.sequence_length != len(payload.display_sequence):
                raise MemoryEvaluationError(
                    f"sequence_length ({payload.sequence_length}) contradicts actual display_sequence length ({len(payload.display_sequence)})."
                )
            seq_len = len(payload.display_sequence)
            if seq_len < constraints.min_sequence_length or seq_len > constraints.max_sequence_length:
                raise MemoryEvaluationError(
                    f"Sequence length ({seq_len}) is outside permitted range "
                    f"[{constraints.min_sequence_length}, {constraints.max_sequence_length}] "
                    f"for difficulty '{constraints.difficulty_level}'."
                )

            # Palette subset verification if palette provided
            if payload.palette:
                palette_set = set(payload.palette)
                for item in payload.display_sequence:
                    if item not in palette_set:
                        raise MemoryEvaluationError(
                            f"Display sequence item '{item}' is not present in provided palette {payload.palette}."
                        )

            authoritative_answer = list(payload.display_sequence)

        elif mode == "spatial_pattern_recall":
            if payload.display_sequence is not None or payload.palette is not None or payload.path_steps is not None:
                raise MemoryEvaluationError(
                    "Malformed field combination: 'spatial_pattern_recall' must not contain sequence fields (display_sequence, palette) or path_steps."
                )
            if payload.matrix_size is None:
                raise MemoryEvaluationError(
                    "spatial_pattern_recall requires 'matrix_size'."
                )
            if payload.matrix_size < constraints.min_matrix_size or payload.matrix_size > constraints.max_matrix_size:
                raise MemoryEvaluationError(
                    f"matrix_size ({payload.matrix_size}) is outside permitted range "
                    f"[{constraints.min_matrix_size}, {constraints.max_matrix_size}] "
                    f"for difficulty '{constraints.difficulty_level}'."
                )
            if payload.grid_dimension is not None:
                expected_grid = f"{payload.matrix_size}x{payload.matrix_size}"
                if payload.grid_dimension.strip().lower() != expected_grid:
                    raise MemoryEvaluationError(
                        f"grid_dimension '{payload.grid_dimension}' contradicts matrix_size {payload.matrix_size} (expected '{expected_grid}')."
                    )
            if not payload.highlighted_cells:
                raise MemoryEvaluationError(
                    "spatial_pattern_recall requires non-empty 'highlighted_cells'."
                )

            cell_count = len(payload.highlighted_cells)
            if cell_count < constraints.min_highlight_count or cell_count > constraints.max_highlight_count:
                raise MemoryEvaluationError(
                    f"Highlighted cell count ({cell_count}) is outside permitted range "
                    f"[{constraints.min_highlight_count}, {constraints.max_highlight_count}] "
                    f"for difficulty '{constraints.difficulty_level}'."
                )

            # Coordinate validation without clamping & duplicate cell rejection
            seen_cells: Set[Tuple[int, int]] = set()
            for idx, cell in enumerate(payload.highlighted_cells):
                r, c = cls.validate_coordinate(cell, payload.matrix_size, "highlighted_cells", idx)
                if (r, c) in seen_cells:
                    raise MemoryEvaluationError(
                        f"Duplicate cell coordinate [{r}, {c}] detected at highlighted_cells[{idx}]."
                    )
                seen_cells.add((r, c))

            # Authoritative answer is canonical sorted representation of coordinates
            authoritative_answer = sorted(payload.highlighted_cells)

        elif mode == "dynamic_spatial_path":
            if constraints.max_path_length == 0:
                raise MemoryEvaluationError(
                    f"dynamic_spatial_path is not allowed for difficulty '{constraints.difficulty_level}'."
                )
            if payload.display_sequence is not None or payload.palette is not None or payload.highlighted_cells is not None:
                raise MemoryEvaluationError(
                    "Malformed field combination: 'dynamic_spatial_path' must not contain sequence fields (display_sequence, palette) or highlighted_cells."
                )
            if payload.matrix_size is None:
                raise MemoryEvaluationError(
                    "dynamic_spatial_path requires 'matrix_size'."
                )
            if payload.matrix_size < constraints.min_matrix_size or payload.matrix_size > constraints.max_matrix_size:
                raise MemoryEvaluationError(
                    f"matrix_size ({payload.matrix_size}) is outside permitted range "
                    f"[{constraints.min_matrix_size}, {constraints.max_matrix_size}] "
                    f"for difficulty '{constraints.difficulty_level}'."
                )
            if payload.grid_dimension is not None:
                expected_grid = f"{payload.matrix_size}x{payload.matrix_size}"
                if payload.grid_dimension.strip().lower() != expected_grid:
                    raise MemoryEvaluationError(
                        f"grid_dimension '{payload.grid_dimension}' contradicts matrix_size {payload.matrix_size} (expected '{expected_grid}')."
                    )
            if not payload.path_steps:
                raise MemoryEvaluationError(
                    "dynamic_spatial_path requires non-empty 'path_steps'."
                )

            path_len = len(payload.path_steps)
            if path_len < constraints.min_path_length or path_len > constraints.max_path_length:
                raise MemoryEvaluationError(
                    f"Path length ({path_len}) is outside permitted range "
                    f"[{constraints.min_path_length}, {constraints.max_path_length}] "
                    f"for difficulty '{constraints.difficulty_level}'."
                )

            # Continuity & coordinate validation
            cls.validate_path_continuity(payload.path_steps, payload.matrix_size)

            authoritative_answer = list(payload.path_steps)

        else:
            raise MemoryEvaluationError(f"Unsupported memory recall_mode '{mode}'.")

        # 4. Optional proposed_answer consistency check
        if payload.proposed_answer is not None:
            if mode == "spatial_pattern_recall":
                if not isinstance(payload.proposed_answer, list):
                    raise MemoryEvaluationError("proposed_answer for spatial_pattern_recall must be a list of coordinates.")
                try:
                    proposed_set = {tuple(c) for c in payload.proposed_answer if isinstance(c, list) and len(c) == 2}
                    authoritative_set = {tuple(c) for c in authoritative_answer}
                except Exception as exc:
                    raise MemoryEvaluationError(f"Malformed proposed_answer coordinates: {exc}") from exc

                if proposed_set != authoritative_set:
                    raise MemoryEvaluationError(
                        f"LLM proposed answer {payload.proposed_answer} conflicts with derived authoritative answer {authoritative_answer}."
                    )
            else:
                if payload.proposed_answer != authoritative_answer:
                    raise MemoryEvaluationError(
                        f"LLM proposed answer {payload.proposed_answer} conflicts with derived authoritative answer {authoritative_answer}."
                    )

        return payload, authoritative_answer

    @classmethod
    def validate_and_compute_payload(
        cls,
        raw_payload: Union[MemoryChallengePayload, Dict[str, Any]],
        difficulty_level: str,
    ) -> Tuple[MemoryChallengePayload, Any]:
        """Validate raw dictionary or model payload and derive authoritative answer."""
        if isinstance(raw_payload, dict):
            try:
                payload_model = MemoryChallengePayload(**raw_payload)
            except Exception as exc:
                raise MemoryEvaluationError(f"Malformed memory challenge payload: {exc}") from exc
        elif isinstance(raw_payload, MemoryChallengePayload):
            payload_model = raw_payload
        else:
            raise MemoryEvaluationError(
                f"Payload must be a dictionary or MemoryChallengePayload, got {type(raw_payload).__name__}."
            )

        return cls.validate_and_derive_answer(payload_model, difficulty_level)
