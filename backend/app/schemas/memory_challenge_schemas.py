"""Pydantic schemas and data contracts for AI-Generated Memory Challenges (Phase 4.3).

Defines:
- MemoryChallengePayload: Structured payload for memory challenge content.
  Enforces extra="forbid" to strictly reject unexpected fields, validates data types,
  and supports the four canonical memory recall modes without number guessing.
"""
from typing import Any, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# The four canonical supported GenAI memory recall modes
VALID_RECALL_MODES = {
    "visual_sequence",
    "spatial_pattern_recall",
    "dynamic_spatial_path",
    "symbol_chronological_order",
}


class MemoryChallengePayload(BaseModel):
    """Complete structured payload for an AI-generated memory challenge.

    Enclosed inside ValidatedChallengeContent.content_payload.
    Strictly forbids unexpected fields via extra="forbid" and prevents type coercion via strict=True.
    """

    recall_mode: str = Field(
        ...,
        description=(
            "Canonical memory recall mode: 'visual_sequence', 'spatial_pattern_recall', "
            "'dynamic_spatial_path', or 'symbol_chronological_order'"
        ),
    )
    sequence_length: Optional[int] = Field(
        None,
        ge=2,
        le=12,
        description="Number of items in an ordered sequence challenge",
    )
    display_sequence: Optional[List[str]] = Field(
        None,
        min_length=2,
        max_length=12,
        description="Ordered list of non-numeric visual items or symbols to memorize",
    )
    palette: Optional[List[str]] = Field(
        None,
        min_length=2,
        max_length=16,
        description="Available selection palette of items or symbols for recall",
    )
    matrix_size: Optional[int] = Field(
        None,
        ge=2,
        le=6,
        description="Dimension N of the N x N spatial grid",
    )
    highlighted_cells: Optional[List[List[int]]] = Field(
        None,
        min_length=2,
        max_length=25,
        description="List of [row, col] coordinates for spatial pattern recall",
    )
    path_steps: Optional[List[List[int]]] = Field(
        None,
        min_length=2,
        max_length=15,
        description="Ordered list of [row, col] coordinates for dynamic spatial path recall",
    )
    grid_dimension: Optional[str] = Field(
        None,
        max_length=10,
        description="String representation of grid dimensions (e.g., '3x3', '4x4')",
    )
    display_duration_seconds: int = Field(
        default=5,
        ge=2,
        le=20,
        description="Seconds items or pattern remain visible during presentation",
    )
    time_limit_seconds: int = Field(
        default=30,
        ge=10,
        le=120,
        description="Allocated time limit in seconds for user recall submission",
    )
    proposed_answer: Optional[Any] = Field(
        None,
        description="Untrusted LLM-proposed answer; validated independently by MemoryAnswerValidator",
    )

    # Strictly reject unexpected fields and prevent type coercion
    model_config = ConfigDict(from_attributes=True, extra="forbid", strict=True)

    @field_validator("recall_mode")
    @classmethod
    def validate_recall_mode(cls, v: str) -> str:
        clean = v.strip().lower() if isinstance(v, str) else ""
        if clean not in VALID_RECALL_MODES:
            raise ValueError(
                f"Invalid recall_mode '{v}'. Must be one of: {sorted(list(VALID_RECALL_MODES))}."
            )
        return clean

    @field_validator("display_sequence", "palette")
    @classmethod
    def validate_string_lists(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return None
        if not isinstance(v, list):
            raise ValueError("Must be a list of strings.")
        for idx, item in enumerate(v):
            if not isinstance(item, str):
                raise ValueError(f"Item at index {idx} must be a string, got {type(item).__name__}.")
            if not item.strip():
                raise ValueError(f"Item at index {idx} cannot be empty or whitespace only.")
        return [item.strip() for item in v]

    @field_validator("highlighted_cells", "path_steps")
    @classmethod
    def validate_coordinate_lists(cls, v: Optional[List[List[int]]]) -> Optional[List[List[int]]]:
        if v is None:
            return None
        if not isinstance(v, list):
            raise ValueError("Coordinates must be a list of coordinate pairs.")
        for idx, coord in enumerate(v):
            if not isinstance(coord, list) or len(coord) != 2:
                raise ValueError(f"Coordinate at index {idx} must be a 2-element [row, col] list.")
            r, c = coord
            if not isinstance(r, int) or isinstance(r, bool) or not isinstance(c, int) or isinstance(c, bool):
                raise ValueError(f"Coordinate at index {idx} values must be integers, got [{type(r).__name__}, {type(c).__name__}].")
        return v

    @model_validator(mode="after")
    def validate_mode_and_field_consistency(self) -> "MemoryChallengePayload":
        mode = self.recall_mode
        if mode in ("visual_sequence", "symbol_chronological_order"):
            if self.matrix_size is not None or self.grid_dimension is not None or self.highlighted_cells is not None or self.path_steps is not None:
                raise ValueError(
                    f"Malformed field combination: '{mode}' must not contain spatial/grid fields (matrix_size, grid_dimension, highlighted_cells, path_steps)."
                )
            if self.sequence_length is not None and self.display_sequence is not None:
                if self.sequence_length != len(self.display_sequence):
                    raise ValueError(
                        f"sequence_length ({self.sequence_length}) must exactly match display_sequence length ({len(self.display_sequence)})."
                    )
        elif mode == "spatial_pattern_recall":
            if self.display_sequence is not None or self.palette is not None or self.path_steps is not None:
                raise ValueError(
                    "Malformed field combination: 'spatial_pattern_recall' must not contain sequence fields (display_sequence, palette) or path_steps."
                )
            if self.matrix_size is not None and self.grid_dimension is not None:
                expected_grid = f"{self.matrix_size}x{self.matrix_size}"
                if self.grid_dimension.strip().lower() != expected_grid:
                    raise ValueError(
                        f"grid_dimension '{self.grid_dimension}' contradicts matrix_size {self.matrix_size} (expected '{expected_grid}')."
                    )
        elif mode == "dynamic_spatial_path":
            if self.display_sequence is not None or self.palette is not None or self.highlighted_cells is not None:
                raise ValueError(
                    "Malformed field combination: 'dynamic_spatial_path' must not contain sequence fields (display_sequence, palette) or highlighted_cells."
                )
            if self.matrix_size is not None and self.grid_dimension is not None:
                expected_grid = f"{self.matrix_size}x{self.matrix_size}"
                if self.grid_dimension.strip().lower() != expected_grid:
                    raise ValueError(
                        f"grid_dimension '{self.grid_dimension}' contradicts matrix_size {self.matrix_size} (expected '{expected_grid}')."
                    )
        return self
