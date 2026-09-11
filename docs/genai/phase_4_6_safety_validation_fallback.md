# Phase 4.6: Safety Validation, Bounded Retry & Deterministic Fallback Specification

**SmartWake AI** — Personalized Adaptive Smart Alarm Clock  
**Package:** `backend.app.services.genai` & `backend.app.schemas`  
**Status:** Completed & Tested (Phase 4.6 Fast-Track: 4.6.1 – 4.6.8)

---

## 1. Overview & Architecture Boundary

The Phase 4.6 Safety & Validation layer guards the SmartWake AI challenge generation pipeline. It sits between raw/untrusted GenAI outputs and user-facing alarm execution. Its core mission is ensuring that **no alarm ever fails to ring or presents an unsafe/malformed challenge to a waking user**, regardless of LLM errors, prompt injection, invalid outputs, rate limits, or network timeouts.

```
Untrusted GenAI / Provider Output
              │
              ▼
┌───────────────────────────────────────┐
│ 1. Common Output Validation           │  (CommonOutputSafetyValidator)
│    - Structural integrity             │
│    - Canonical type & difficulty check│
│    - Prompt injection & harmful text  │
└──────────────────┬────────────────────┘
                   │ Pass
                   ▼
┌───────────────────────────────────────┐
│ 2. Domain-Specific Safety Validation  │  (DomainSafetyValidator)
│    - Math: solvable, bounds, no div/0 │
│    - Memory: no numeric leak/guessing │
│    - Tongue Twister: length, sounds   │
│    - Physical: exertion/duration caps │
└──────────────────┬────────────────────┘
                   │
                   ▼
       SafetyValidationReport
     (is_safe = True / False)
```

---

## 2. Validation Architecture

Validation strictly follows a two-stage sequential evaluation producing an immutable `SafetyValidationReport`. Content is **never silently sanitized**; invalid content is strictly rejected.

### Stage 1: Common Output Validation (`CommonOutputSafetyValidator`)
- **Structural Integrity:** Rejects non-dict payloads, missing required fields (`title`, `instructions`, `content_payload`), or empty text.
- **Contract Preservation:** Verifies `challenge_type` matches expected canonical type and `difficulty_level` matches expected difficulty.
- **Safety & Injection Defense:** Inspects text fields for prompt injection indicators (`ignore previous instructions`, `bypass safety rules`) and toxic/harmful keywords using regex pattern boundaries.

### Stage 2: Domain-Specific Validation (`DomainSafetyValidator`)
- **Math Challenges:**
  - Validates arithmetic expressions via `SafeArithmeticEvaluator` and `MATH_GENERATION_CONSTRAINTS`.
  - Rejects division by zero (`MATH_DIVISION_BY_ZERO`), unparseable expressions, and operand/result bounds violations (`MATH_UNSOLVABLE`).
  - Verifies deterministic answer correctness against `expected_answer`.
- **Memory Challenges:**
  - Verifies non-empty sequence/grid.
  - Enforces strict non-numeric constraint: rejects pure numeric sequences and digit strings (`MEMORY_NUMERIC_LEAK`), preventing degradation into number-guessing games.
  - Enforces sequence length bounds per difficulty tier (`MEMORY_OUT_OF_BOUNDS`).
  - Validates palette themes against `MemoryPaletteTheme` (`MEMORY_INVALID_PALETTE`).
- **Tongue Twister Challenges:**
  - Enforces word count limits per difficulty tier (`TWISTER_LENGTH_INVALID`).
  - Validates phonetic alliteration characteristics via `TongueTwisterAnswerValidator.validate_orthographic_sound_pattern` (`TWISTER_POOR_ALLITERATION`).
  - Rejects numeric digits (`0-9`) in passages.
- **Procedural Physical Challenges (Dance & Push-ups):**
  - Reject impossible/unreasonable physical demands (`PHYSICAL_EXERTION_EXCEEDED`).
  - Caps push-up repetitions per difficulty (`easy <= 15`, `medium <= 30`, `hard <= 50`).
  - Caps dance duration (`easy <= 30s`, `medium <= 60s`, `hard <= 90s`) and step counts.

---

## 3. Bounded Retry Boundary (`SafetyRetryOrchestrator`)

Retries are strictly bounded by `ValidationRetryPolicy` to guarantee execution finishes within alarm ringing windows:

- **Max Retries:** Default `1`, maximum allowed `2`. Indefinite loops are structurally impossible.
- **Separation of Concerns:** Validators are pure stateless functions with zero side-effects. Retries are exclusively orchestrated by `SafetyRetryOrchestrator`.
- **Retry Triggers:**
  - Common validation failure $\to$ retry with attempt counter increment.
  - Domain validation failure $\to$ retry with attempt counter increment.
  - Provider timeout (`GenAITimeoutError`) $\to$ retry if budget allows.
  - Rate limit (`GenAIRateLimitError`) $\to$ immediate fallback without retries.

---

## 4. Deterministic Offline Fallback (`DeterministicFallbackResolver`)

When retries are exhausted or a provider failure occurs, the orchestrator triggers deterministic fallback resolution:

- **Zero Network / Zero LLM:** Pre-verified static challenge definitions from `DETERMINISTIC_FALLBACK_CATALOG`.
- **15 Canonical Combinations:** Complete offline coverage across 5 challenge types (`dance`, `math`, `memory`, `tongue_twister`, `push_ups`) $\times$ 3 difficulties (`easy`, `medium`, `hard`).
- **Contract Guarantees:**
  - `preserved_type = True`: The user's selected challenge type is never altered.
  - `preserved_difficulty = True`: Phase 3's authoritative difficulty tier is strictly maintained.
  - Returns typed `FallbackResolution` metadata documenting `fallback_reason`, `trigger_error`, and `fallback_reference_id`.

---

## 5. Provider Failure Path

Provider exceptions are caught cleanly at the orchestration boundary:

```
Provider Invocation
       │
       ├─── GenAITimeoutError ───────────────► Retry if attempts remain; else FallbackReason.PROVIDER_TIMEOUT
       │
       ├─── GenAIRateLimitError ─────────────► Immediate Fallback (FallbackReason.RATE_LIMITED)
       │
       ├─── GenAIProviderUnavailableError ───► Immediate Fallback (FallbackReason.PROVIDER_UNAVAILABLE)
       │
       └─── Unexpected Exception ────────────► Logged safely; FallbackReason.PROVIDER_UNAVAILABLE
```

Raw provider stack traces and error details are never exposed to waking users or challenge payloads. The alarm always presents a valid, safe, difficulty-appropriate challenge.
