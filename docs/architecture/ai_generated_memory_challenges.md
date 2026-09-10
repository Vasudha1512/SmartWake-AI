# AI-Generated Memory Challenges Specification

**Phase 4.3 — AI-Generated Memory Challenges**  
**SmartWake AI** — Personalized Adaptive Smart Alarm Clock  
**Package:** `backend.app.services.genai`

---

## 1. Executive Summary & Purpose

Phase 4.3 establishes the foundation for **AI-Generated Memory Challenges** within SmartWake AI.

Memory challenges stimulate cognitive awakening through visual and spatial recall. Under SmartWake AI's **zero-trust AI architecture**, Generative AI models are untrusted content generators:
- **Strictly Zero Number Guessing:** Memory challenges must never degenerate into number guessing, numeric sequence recall, PIN codes, OTPs, or arithmetic recall.
- **Targeted Non-Numeric Enforcement:** User-facing memory items (colors, shapes, symbols, objects) must be strictly non-numeric. Structural numeric parameters (such as `matrix_size`, `sequence_length`, `display_duration_seconds`, and integer grid coordinates) are permitted.
- **Deterministic Validation & Answer Derivation:** The application independently validates all coordinates without clamping, enforces continuity on dynamic spatial paths, and deterministically derives the authoritative `expected_answer`.
- **Untrusted LLM Answers:** If the LLM proposes an answer that conflicts with the Python-derived answer, the challenge is **rejected immediately**.

```
Authoritative Challenge Type: "memory"
+
Authoritative Concrete Difficulty: "easy" | "medium" | "hard" (from Phase 3 ML)
+
Safe Generation Context: SafePersonalizationContext (sanitized, zero PII)
+
Memory Generation Constraints: MemoryGenerationConstraints (non-numeric, sequence/grid limits)
       ↓
MemoryPromptBuilder (Structured provider prompt with JSON schema)
       ↓
GenAIService / Active Provider (MockGenAIProvider in tests)
       ↓
MemoryChallengePayload (Strict schema, extra="forbid")
       ↓
MemoryAnswerValidator (Targeted non-numeric scan, coordinate bounds, path continuity, answer derivation)
       ↓
ChallengeContentValidator (Framework validation: immutability, payload size, forbidden terms)
       ↓
ValidatedChallengeContent (Internal validated domain model with authoritative expected_answer)
```

---

## 2. Phase 4.3 Architectural Boundaries

1. **Memory Only:** Only GenAI memory generation is implemented. GenAI generation for Dance, Tongue Twister, and Push-ups is deferred to future sub-phases.
2. **Procedural Generators Preserved:** Existing Phase 2.7.3 procedural generators (`_generate_memory`, `_generate_math`, etc.) in `challenge_generation_service.py` are **unmodified**.
3. **Completion Verification Independence:** Existing Phase 2.8 verification engine (`verify_memory`) in `challenge_verification_service.py` is **unmodified**. Phase 4.3 produces answers compatible with its existing verification contract.
4. **Runtime Execution Preserved:** `ChallengeExecutionService` and wake session alarm lifecycles are **unmodified**.
5. **Runtime Contract Decoupling:** `RuntimeChallengeResponse` is **unmodified** (uses `generated_content`). Future Phase 4.7 will map `ValidatedChallengeContent.content_payload` into `RuntimeChallengeResponse.generated_content`.
6. **Zero Database Impact:** Zero ORM models, zero migrations, zero writes to `smartwake.db`.
7. **Zero New Dependencies:** Zero packages added to `requirements.txt`.

---

## 3. Separation of Responsibilities Across Phases

| Phase / Engine | Core Question Answered | Authoritative Output |
|---|---|---|
| **Phase 3 ML (`AdaptiveDecisionEngine`)** | *"How difficult should the memory challenge be?"* | Concrete difficulty: `easy`, `medium`, or `hard`. |
| **Phase 4.3 GenAI (`MemoryChallengeGenerator`)** | *"What memory content should be generated at that already-selected difficulty?"* | `ValidatedChallengeContent` with independently derived `expected_answer`. |
| **Phase 2.8 Verification (`verify_memory`)** | *"Did the user actually recall it correctly during the alarm?"* | `ChallengeVerificationResult` (`is_successful`, score). |

---

## 4. Supported Memory Modes & Difficulty Constraints

### 4.1 Canonical Recall Modes
1. **`visual_sequence`**: Flashing sequence of colored visual tiles (e.g. emerald, amber, azure, coral). User recalls exact sequential order.
2. **`spatial_pattern_recall`**: Illuminated cells in an $N \times N$ matrix grid (e.g. 3x3, 4x4). User recalls illuminated cell locations.
3. **`dynamic_spatial_path`**: Illuminated light tracing a continuous path step-by-step across an $N \times N$ grid. User recreates the path order.
4. **`symbol_chronological_order`**: Sequence of distinct geometric or themed symbols (e.g. triangle, circle, diamond, star, crescent, hexagon). User reconstructs their chronological order.

### 4.2 Bounded Constraints

| Parameter | Easy Tier | Medium Tier | Hard Tier |
|---|---|---|---|
| **Allowed Modes** | `visual_sequence`, `spatial_pattern_recall` | `visual_sequence`, `spatial_pattern_recall`, `dynamic_spatial_path`, `symbol_chronological_order` | `visual_sequence`, `spatial_pattern_recall`, `dynamic_spatial_path`, `symbol_chronological_order` |
| **Sequence Length Range** | 3 to 4 items (default 3) | 4 to 6 items (default 5) | 6 to 8 items (default 7) |
| **Matrix Size ($N \times N$)** | 3 (3x3 grid) | 3 to 4 (3x3 or 4x4 grid) | 4 to 5 (4x4 or 5x5 grid) |
| **Highlight Count Range** | 3 cells (max 4) | 4 to 5 cells (max 6) | 6 to 8 cells (max 10) |
| **Path Length (Dynamic)** | Not permitted | 4 to 5 steps | 6 to 8 steps |
| **Display Duration** | 4 – 5 seconds | 5 – 6 seconds | 6 – 8 seconds |
| **Time Limit** | 20 seconds | 35 seconds | 50 – 60 seconds |

---

## 5. Non-Numeric Policy & Coordinate Rules

### 5.1 Targeted Non-Numeric Memory Enforcement
- **Permitted Structural Numbers:**
  - `matrix_size`: integer representing grid dimension.
  - `sequence_length`: integer representing item count.
  - `display_duration_seconds` & `time_limit_seconds`: integers representing timing parameters.
  - Grid cell coordinates: pairs of integers `[row, col]`.
- **Forbidden User-Memory Items:**
  - Memory item strings (`display_sequence`, `palette`) are scanned against `^\s*-?\d+(\.\d+)?\s*$` and arithmetic patterns (`5 + 4`). Digit strings like `"42"` or `"3819"` are rejected.
- **Context-Aware Forbidden Concept Patterns:**
  - Rejects targeted numeric-memory phrases: `"guess the number"`, `"guess_number"`, `"number_guessing"`, `"numeric sequence"`, `"pin code"`, `"otp"`, `"passcode"`, `"digit sequence"`, `"number recall"`, `"numeric code"`, `"numeric_memory"`.
  - Common words like "code" or "guess" in ordinary non-numeric sentences are not rejected.

### 5.2 Deterministic Coordinate Bounds (No Clamping)
- For every cell `[r, c]` in `highlighted_cells` or `path_steps`:
  - $0 \le r < \text{matrix\_size}$ and $0 \le c < \text{matrix\_size}$.
  - Invalid coordinates are **never clamped or modified**; they trigger immediate rejection (`MemoryEvaluationError`).
  - In `spatial_pattern_recall`, all coordinates must be unique (duplicate coordinates rejected).

### 5.3 Dynamic Spatial Path Continuity
- Consecutive steps $(r_i, c_i)$ and $(r_{i+1}, c_{i+1})$ must be strictly adjacent:
  $$\max(|r_{i+1} - r_i|, |c_{i+1} - c_i|) = 1$$
- Stationary steps (distance $= 0$) and non-adjacent jumps (distance $> 1$) are deterministically rejected.
- Path steps must be distinct cells (no self-intersecting loops).

---

## 6. Authoritative Answer Derivation & Trust Boundary

### 6.1 Authoritative Derivation
The application derives the authoritative `expected_answer` using deterministic logic:
1. **`visual_sequence` & `symbol_chronological_order`**:
   `expected_answer = list(payload.display_sequence)`
2. **`spatial_pattern_recall`**:
   `expected_answer = sorted(payload.highlighted_cells)` (canonical sorted coordinate list)
3. **`dynamic_spatial_path`**:
   `expected_answer = list(payload.path_steps)` (canonical ordered coordinate list)

### 6.2 Proposed Answer Trust Handling
- If `proposed_answer` is supplied by the LLM:
  - For spatial patterns: compared as set of coordinates `set(tuple(c) for c in proposed) == set(tuple(c) for c in derived)`.
  - For sequences: compared in exact order `proposed == derived`.
  - If mismatch: raise `MemoryEvaluationError("LLM proposed answer conflicts with derived authoritative answer")`.
- If `proposed_answer` is omitted: derived answer becomes authoritative automatically.

---

## 7. Personalization & Safe Duration Scaling

`MemoryPromptBuilder` consumes `SafePersonalizationContext`:
- **Bounded Duration Scaling:** `desired_duration_seconds` can only calibrate `sequence_length` or `highlight_count` **within the already-authoritative Phase 3 difficulty bounds**:
  - Easy: strictly clamped within `[3, 4]`.
  - Medium: strictly clamped within `[4, 6]`.
  - Hard: strictly clamped within `[6, 8]`.
  - **It must NEVER escalate or downgrade the concrete difficulty tier**.
- **Theming & Language:** `preferred_theme` guides non-numeric item themes (e.g. "morning coffee items", "nature shapes").
- **Identity Privacy Guarantee:** Prompts never reference `user_id`, `email`, `session_id`, `alarm_id`, or tokens.

---

## 8. Exception Hierarchy

```
SmartWakeException
└── GenAIError
    ├── GenAIConfigurationError
    ├── GenAIProviderUnavailableError
    ├── GenAITimeoutError
    ├── GenAIRateLimitError
    ├── GenAIValidationError
    │   └── ChallengeContentValidationError
    │       ├── MathEvaluationError (Phase 4.2)
    │       └── MemoryEvaluationError (Phase 4.3: non-numeric violations, coordinate out of bounds, path continuity)
    │
    ├── MathChallengeGenerationError (Phase 4.2)
    └── MemoryChallengeGenerationError (Phase 4.3: pipeline coordination, provider dispatch error)
```

---

## 9. Future Phase 4.7 Runtime Adapter Roadmap

In Phase 4.3:
- Output: `ValidatedChallengeContent(challenge_type="memory", content_payload={...}, expected_answer=...)`.

In Phase 4.7:
- An adapter will translate:
  `ValidatedChallengeContent.content_payload` → adapter → `RuntimeChallengeResponse.generated_content`.
- The existing runtime generator (`_generate_memory`) and `RuntimeChallengeResponse` remain unmodified.
