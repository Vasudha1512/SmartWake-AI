"""Challenge Content Validation Engine for SmartWake AI (Phase 4.1).

Validates that generated challenge content is structurally well-formed, bounded,
faithful to the requested challenge type and difficulty, and strictly free of
forbidden concepts (such as number guessing in memory challenges).

DISTINCTION:
- Content Validation (Phase 4.1): "Is this generated challenge structurally valid and safe?"
- Completion Verification (Phase 2.8): "Did the user actually complete or solve it?"
"""
import json
from typing import Any, Dict, List, Optional, Set

from backend.app.core.exceptions import ChallengeContentValidationError
from backend.app.schemas.challenge_content_schemas import (
    ChallengeGenerationConstraints,
    ContentValidationResult,
    ValidatedChallengeContent,
)
from backend.app.services.genai.challenge_constraints import get_challenge_constraints


class ChallengeContentValidator:
    """Pure in-memory validation engine for generated challenge content."""

    @classmethod
    def validate(
        cls,
        raw_content: Dict[str, Any],
        requested_type: str,
        requested_difficulty: str,
        constraints: Optional[ChallengeGenerationConstraints] = None,
        generation_metadata: Optional[Dict[str, Any]] = None,
    ) -> ContentValidationResult:
        """Validate raw provider content against framework boundaries and constraints.

        Args:
            raw_content: Dictionary output returned by a GenAI provider.
            requested_type: Canonical challenge type requested.
            requested_difficulty: Concrete difficulty tier requested ('easy', 'medium', 'hard').
            constraints: Optional pre-resolved constraints. If None, resolved dynamically.
            generation_metadata: Optional provider/model telemetry metadata.

        Returns:
            ContentValidationResult: Validation outcome with errors or validated content model.
        """
        errors: List[str] = []

        if not isinstance(raw_content, dict):
            return ContentValidationResult(
                is_valid=False,
                errors=["Generated content must be a non-empty JSON object / dictionary."],
                validated_content=None,
            )

        # 1. Resolve constraints
        effective_constraints = constraints or get_challenge_constraints(
            requested_type, requested_difficulty
        )

        clean_req_type = requested_type.strip().lower()
        clean_req_diff = requested_difficulty.strip().lower()

        # 2. Verify challenge_type immutability
        gen_type = str(raw_content.get("challenge_type", "")).strip().lower()
        if not gen_type:
            errors.append("Missing required field 'challenge_type' in generated content.")
        elif gen_type != clean_req_type:
            errors.append(
                f"Challenge type mutation detected: requested '{clean_req_type}', "
                f"but generated content specified '{gen_type}'."
            )

        # 3. Verify difficulty_level immutability and concrete tier
        gen_diff = str(raw_content.get("difficulty_level", "")).strip().lower()
        if not gen_diff:
            errors.append("Missing required field 'difficulty_level' in generated content.")
        elif gen_diff != clean_req_diff:
            errors.append(
                f"Difficulty level mutation detected: requested '{clean_req_diff}', "
                f"but generated content specified '{gen_diff}'."
            )
        elif gen_diff not in ("easy", "medium", "hard"):
            errors.append(
                f"Generated difficulty '{gen_diff}' is invalid. Must be concrete: 'easy', 'medium', or 'hard'."
            )

        # 4. Validate title
        title = raw_content.get("title")
        if not title or not isinstance(title, str) or not title.strip():
            errors.append("Missing or empty required string field 'title'.")
        else:
            clean_title = title.strip()
            if len(clean_title) < 3:
                errors.append(f"Title is too short ({len(clean_title)} chars; minimum 3).")
            elif len(clean_title) > effective_constraints.max_title_length:
                errors.append(
                    f"Title exceeds maximum length ({len(clean_title)} > {effective_constraints.max_title_length})."
                )

        # 5. Validate instructions
        instructions = raw_content.get("instructions")
        if not instructions or not isinstance(instructions, str) or not instructions.strip():
            errors.append("Missing or empty required string field 'instructions'.")
        else:
            clean_inst = instructions.strip()
            if len(clean_inst) < 10:
                errors.append(f"Instructions too short ({len(clean_inst)} chars; minimum 10).")
            elif len(clean_inst) > effective_constraints.max_instructions_length:
                errors.append(
                    f"Instructions exceed maximum length ({len(clean_inst)} > {effective_constraints.max_instructions_length})."
                )

        # 6. Validate content_payload
        payload = raw_content.get("content_payload")
        if payload is None:
            # Check for alternative key 'content' if provider structured under 'content'
            payload = raw_content.get("content")

        if payload is None or not isinstance(payload, dict):
            errors.append("Missing or invalid 'content_payload' (must be a non-empty dictionary).")
        else:
            # Check serialized size
            try:
                serialized = json.dumps(payload)
                byte_size = len(serialized.encode("utf-8"))
                if byte_size > effective_constraints.max_payload_bytes:
                    errors.append(
                        f"content_payload byte size ({byte_size}) exceeds limit ({effective_constraints.max_payload_bytes})."
                    )
            except (TypeError, ValueError) as exc:
                errors.append(f"content_payload is not JSON serializable: {exc}")

            # Check required generic payload keys if defined
            for req_key in effective_constraints.required_payload_keys:
                if req_key not in payload:
                    errors.append(f"content_payload is missing required key '{req_key}'.")

        # 7. Scan for forbidden concepts (e.g., number guessing in memory)
        content_dump_lower = json.dumps(raw_content).lower()
        for forbidden in effective_constraints.forbidden_terms:
            if forbidden in content_dump_lower:
                errors.append(
                    f"Generated content contains forbidden concept '{forbidden}'."
                )

        # 8. Check verification mode and duration
        verif_mode = raw_content.get("verification_mode") or effective_constraints.verification_mode
        min_duration = int(raw_content.get("min_duration_seconds", effective_constraints.min_duration_seconds))
        if min_duration < 5:
            min_duration = effective_constraints.min_duration_seconds

        if errors:
            return ContentValidationResult(
                is_valid=False,
                errors=errors,
                validated_content=None,
            )

        # Construct validated domain model
        validated_obj = ValidatedChallengeContent(
            challenge_type=clean_req_type,
            difficulty_level=clean_req_diff,
            title=str(title).strip(),
            instructions=str(instructions).strip(),
            content_payload=payload if isinstance(payload, dict) else {},
            parameters=raw_content.get("parameters", {}),
            expected_answer=raw_content.get("expected_answer"),
            verification_mode=str(verif_mode),
            min_duration_seconds=min_duration,
            generation_metadata=generation_metadata or {},
        )

        return ContentValidationResult(
            is_valid=True,
            errors=[],
            validated_content=validated_obj,
        )

    @classmethod
    def validate_or_raise(
        cls,
        raw_content: Dict[str, Any],
        requested_type: str,
        requested_difficulty: str,
        constraints: Optional[ChallengeGenerationConstraints] = None,
        generation_metadata: Optional[Dict[str, Any]] = None,
    ) -> ValidatedChallengeContent:
        """Validate content and return ValidatedChallengeContent or raise ChallengeContentValidationError."""
        res = cls.validate(
            raw_content=raw_content,
            requested_type=requested_type,
            requested_difficulty=requested_difficulty,
            constraints=constraints,
            generation_metadata=generation_metadata,
        )
        if not res.is_valid:
            error_summary = "; ".join(res.errors)
            raise ChallengeContentValidationError(f"Challenge content validation failed: {error_summary}")
        return res.validated_content
