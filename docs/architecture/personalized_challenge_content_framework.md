# Personalized Challenge Content Framework Specification

**Phase 4.1 — Personalized Challenge Content Framework**  
**SmartWake AI** — Personalized Adaptive Smart Alarm Clock

---

## 1. Executive Summary

Phase 4.1 establishes the **Personalized Challenge Content Framework** for SmartWake AI.

The framework transforms authoritative inputs into a standardized, validated challenge content domain model:

```
Authoritative Challenge Type (User Selection)
+
Authoritative Concrete Difficulty (Phase 3 ML / Fixed User Preference)
+
Safe Personalization Context (Identity-free, sanitized, bounded parameters)
+
Challenge Generation Constraints (Framework structural rules & generic constraint slots)
               ↓
Structured GenAI Challenge Request (GenAIContentRequest)
               ↓
GenAIService / Active Provider (Phase 4.0 Foundation / BaseGenAIProvider)
               ↓
Challenge Content Validation Engine (Pure In-Memory Validator)
               ↓
Validated Structured Challenge Content (ValidatedChallengeContent)
```

---

## 2. Core Architectural Separation of Concerns

SmartWake AI maintains strict boundaries across the alarm challenge lifecycle:

1. **Phase 3 ML (`AdaptiveDecisionEngine`):**
   - Authoritative for *"How difficult should the challenge be?"*
   - Outputs a concrete difficulty: `easy`, `medium`, or `hard`.
   - Preserves user-selected challenge type.
2. **Phase 4 GenAI (`GenAIService` & `ChallengeContentFramework`):**
   - Generates *"What fresh challenge content should be presented at the already-selected type and concrete difficulty?"*
   - Applies structural boundaries, content sanitization, and generic constraint slots.
   - Operates purely as a content generator, never as a decision authority.
3. **Phase 2.8 Verification (`verify_challenge`):**
   - Authoritative for *"Did the user actually complete or solve the challenge during the alarm session?"*
   - Purely deterministic, evaluating user submissions against the challenge's expected answer.

---

## 3. Four Core Architectural Guarantees

### 3.1 Complete Exclusion of Database Identity
- `SafePersonalizationContext` contains **zero database identity**.
- Attributes such as `user_id`, `email`, `name`, `phone`, `alarm_id`, `session_id`, `password`, `auth tokens`, and raw database records are strictly forbidden and rejected.
- Database identity remains isolated exclusively at the backend application/service layer.

### 3.2 Bounded and Sanitized Topic Constraints
- To prevent prompt injection or unbounded text bloat, `disallowed_topics` is strictly constrained:
  - Maximum count: **10 topics maximum**.
  - Maximum length: **30 characters per topic maximum**.
  - Maximum total length: **300 characters combined maximum**.
  - Character safety: permits only alphanumeric characters, spaces, hyphens, and underscores (`^[a-zA-Z0-9_\- ]+$`). Control characters, newlines, and illegal symbols are rejected.
  - Topics are deduplicated and normalized to lowercase.
- *Security Note:* Context sanitization and strict topic bounds reduce unbounded-input and prompt-injection risk, but do not claim to completely eliminate all adversarial prompt injection attacks.

### 3.3 Separation of Framework Constraints vs. Domain Validation
- Phase 4.1 establishes the **generic framework mechanism and constraint slots**:
  - Validates required fields (`title`, `instructions`, `content_payload`, `verification_mode`).
  - Asserts challenge type immutability (`returned_type == requested_type`).
  - Asserts concrete difficulty immutability (`returned_diff == requested_diff` in `{"easy", "medium", "hard"}`).
  - Enforces forbidden term rejection (e.g. `number_guessing` in Memory).
  - Enforces payload size (16 KB max) and text length limits.
- Phase 4.1 does **NOT** implement domain-specific generators or deep domain validation:
  - **Phase 4.2:** Math arithmetic problem generators, word problems, and equation solvers.
  - **Phase 4.3:** Memory spatial matrices, dynamic paths, and visual sequence recall.
  - **Phase 4.4:** Tongue Twister phonetic passages, alliterative friction, and word counts.
  - **Phase 4.5:** AI-powered behavioral personalization algorithms.

### 3.4 Semantic Separation: `desired_duration_seconds`
- The personalization context field is explicitly named **`desired_duration_seconds`** (bounded to `[5, 300]` seconds).
- This avoids semantic confusion with ML `target_duration_seconds` (historical training outcome labels).
- `desired_duration_seconds` is used solely as a styling preference to inform challenge length. It is never treated as an ML training target, does not introduce post-challenge outcome leakage, and cannot alter alarm scheduling.

---

## 4. Content Validation vs. Completion Verification

A critical distinction is enforced between **Content Validation** and **Completion Verification**:

| Aspect | Content Validation (Phase 4.1) | Completion Verification (Phase 2.8) |
|---|---|---|
| **Question** | *"Is this generated challenge structurally valid, safely bounded, non-empty, and faithful to the requested type and difficulty before being presented to the user?"* | *"Did the user actually complete, solve, or perform the challenge correctly?"* |
| **Component** | `ChallengeContentValidator` in `backend/app/services/genai/` | `verify_challenge` in `backend/app/services/challenge_verification_service.py` |
| **Inputs** | Raw generated payload from LLM/mock provider | User submission payload vs. `expected_answer` |
| **Authority** | Framework safety and schema enforcer | Alarm dismissal gateway |

---

## 5. Framework Architecture & Components

### 5.1 `SafePersonalizationContext` (`challenge_content_schemas.py`)
Encapsulates non-identifiable parameters:
- `desired_duration_seconds`: Optional integer (5–300).
- `current_session_snooze_count`: Integer (0–20).
- `current_attempt_number`: Integer (1–10).
- `preferred_theme`: Optional string (max 50 chars, no control characters).
- `language`: String (default `"en"`).
- `disallowed_topics`: Bounded string list (max 10 items, max 30 chars/item, max 300 chars total).

### 5.2 Generic Constraint Slots (`challenge_constraints.py`)
Provides extensible framework slots per canonical type:
- `math`: `verification_mode="math_standard"`, `required_payload_keys=["questions"]`, `forbidden_terms={"number_guessing"}`.
- `memory`: `verification_mode="memory_standard"`, `required_payload_keys=["recall_mode"]`, `forbidden_terms={"number_guessing", "guess_number", "numeric_memory"}`.
- `tongue_twister`: `verification_mode="tongue_twister_standard"`, `required_payload_keys=["passage"]`.
- `dance`: `verification_mode="dance_standard"`, `required_payload_keys=["steps"]`.
- `push_ups`: `verification_mode="push_ups_standard"`, `required_payload_keys=["target_repetitions"]`.

Supports runtime extension via `register_challenge_constraints(type, builder)` for future sub-phases.

### 5.3 `ChallengeContentValidator` (`challenge_content_validator.py`)
Pure in-memory validation engine checking:
1. Type immutability.
2. Difficulty immutability and concrete tier.
3. Title length (`[3, max_title_length]`).
4. Instructions length (`[10, max_instructions_length]`).
5. Content payload presence, dictionary structure, and byte size (<= 16 KB).
6. Forbidden concept scan across all payload text.
7. Verification mode presence.

### 5.4 `ChallengeContentFramework` (`challenge_content_framework.py`)
High-level orchestrator:
1. `sanitize_personalization_context(...)`: Strips or rejects unauthorized keys.
2. `build_generation_request(...)`: Formulates `GenAIContentRequest` with `user_id=None`.
3. `generate_and_validate(...)`: Dispatches request through `GenAIService` and validates response through `ChallengeContentValidator`.

---

## 6. Provider Independence & Offline Testing

- The framework operates exclusively over `GenAIService` / `BaseGenAIProvider`.
- Contains zero Gemini-specific or vendor-specific code.
- Fully compatible with `MockGenAIProvider` for 100% offline, deterministic CI/CD testing without network access or API credentials.

---

## 7. Zero Database & Zero Dependency Impact

- **Database:** Zero new tables, zero new columns, zero migrations. `smartwake.db` remains untouched.
- **Dependencies:** Zero new third-party packages in `requirements.txt`.
