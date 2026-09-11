# Phase 4.6: Safety Validation, Bounded Retry & Deterministic Fallback Specification

**SmartWake AI** — Personalized Adaptive Smart Alarm Clock  
**Package:** `backend.app.services.genai` & `backend.app.schemas`  
**Status:** Completed, Integrated & Formally Audited (Phase 4.6 Steps 1–11)

---

## 1. Overview & Architecture Boundary

The Phase 4.6 Safety & Validation layer guards the SmartWake AI challenge generation pipeline. It sits between raw/untrusted GenAI outputs and user-facing challenge execution. Its architectural guarantee is that **any GenAI generation error, provider failure, or content safety violation has a strictly bounded path to a validated deterministic offline fallback whenever fallback is available**.

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

## 2. Detailed Validation Architecture

### A. Common Output Validation (`CommonOutputSafetyValidator`)
- **Structural Sanity:** Verifies payload is a dictionary/object with non-empty required fields (`title`, `instructions`, `content_payload`).
- **Control Character Defense:** Rejects dangerous unprintable control characters (`ord < 32` except `\t`, `\n`, `\r`, and `127`).
- **Prompt Injection Defense:** Scans title and instruction strings for prompt-injection markers (`ignore previous instructions`, `bypass safety rules`, `reveal system prompt`, etc.).
- **Harmful Content Guard:** Scans text fields for self-harm, violent instructions, or hazardous morning wake-up commands.

### B. Domain-Specific Safety Validation (`DomainSafetyValidator`)
- **Math Challenges:**
  - Validates arithmetic expressions via `SafeArithmeticEvaluator` and `MATH_GENERATION_CONSTRAINTS`.
  - Rejects division by zero (`MATH_DIVISION_BY_ZERO`), unparseable expressions, and operand/result bounds violations (`MATH_UNSOLVABLE`).
  - Verifies deterministic answer correctness against `expected_answer`.
- **Memory Challenges:**
  - Verifies non-empty sequence/grid via `display_sequence` or `sequence`.
  - Enforces strict non-numeric constraint: rejects pure numeric sequences and digit strings (`MEMORY_NUMERIC_LEAK`), preventing degradation into number-guessing games.
  - Enforces sequence length bounds per difficulty tier (`MEMORY_OUT_OF_BOUNDS`).
  - Validates palette themes against `MemoryPaletteTheme` (`MEMORY_INVALID_PALETTE`).
- **Tongue Twister Challenges:**
  - Enforces word count limits per difficulty tier (`TWISTER_LENGTH_INVALID`).
  - Validates phonetic alliteration characteristics via `TongueTwisterAnswerValidator.validate_orthographic_sound_pattern` (`TWISTER_POOR_ALLITERATION`).
  - Rejects numeric digits (`0-9`) in passages.
- **Procedural Physical Challenges (Dance & Push-ups):**
  - Rejects impossible/unreasonable physical demands (`PHYSICAL_EXERTION_EXCEEDED`).
  - Caps push-up repetitions per difficulty (`easy <= 15`, `medium <= 30`, `hard <= 50`).
  - Caps dance duration (`easy <= 30s`, `medium <= 60s`, `hard <= 90s`) and step counts (`[2, 30]`).

### C. Type & Difficulty Preservation
- **Type Preservation (Invariant G):** The user-selected canonical challenge type (`dance`, `math`, `memory`, `tongue_twister`, `push_ups`) is immutable. Any output attempting type mutation is strictly rejected (`TYPE_MUTATION`).
- **Difficulty Preservation (Invariant H):** The concrete difficulty tier established by Phase 3 (`easy`, `medium`, `hard`) is immutable. Non-concrete values like `"adaptive"` are rejected (`DIFFICULTY_MUTATION`).

### D. No Silent Sanitization (Invariant I)
Generated content is **never silently sanitized or mutated**. Malformed or unsafe outputs are strictly flagged with typed `SafetyViolation` objects and rejected. The pipeline either obtains genuinely valid content through a clean retry or resolves to an authoritative deterministic fallback.

### E. Privacy & Zero-PII Boundary (Invariant J)
- No user IDs, database entities, ORM models, session tokens, or personal identifiers enter or exit the safety pipeline.
- Diagnostic notes and error logs pass through redaction filters to guarantee zero PII leakage.

---

## 3. Bounded Retry Policy (`ValidationRetryPolicy`)

Retries are strictly managed by `SafetyRetryOrchestrator`:

- **Bounded Execution (Invariant L):** Default `max_retries = 1`, maximum allowed `max_retries = 2`. Attempts are mathematically capped at `attempts_used <= max_retries + 1`, structurally eliminating infinite loops.
- **Separation of Concerns:** Validators are pure stateless functions with zero side-effects. Retries are orchestrated exclusively by `SafetyRetryOrchestrator`.
- **Policy Behavior:**
  - Common / Domain validation failure $\to$ attempt counter increments, bounded retry executed if budget permits.
  - Recoverable provider error (`GenAITimeoutError`) $\to$ retried if attempts remain.
  - Non-retryable error (`GenAIRateLimitError`, `GenAIProviderUnavailableError`) $\to$ drops immediately to fallback without compounding retries.

---

## 4. Deterministic Offline Fallback (`DeterministicFallbackResolver`)

When retries are exhausted or a provider failure occurs, the orchestrator triggers deterministic fallback resolution:

- **Zero Network / Zero LLM (Invariant K):** Backed by `DETERMINISTIC_FALLBACK_CATALOG`, an immutable in-memory registry of pre-verified challenge payloads.
- **15 Canonical Combinations:** Complete coverage across 5 challenge types $\times$ 3 difficulties (`easy`, `medium`, `hard`).
- **Safety Guarantee:** Every single payload in the fallback catalog has been verified to pass 100% of Common and Domain safety rules.
- **Repeatability:** Identical fallback requests deterministically yield identical payloads and metadata across runs.

---

## 5. Provider Failure Path & Resilience

Provider exceptions are caught cleanly at the orchestration boundary without leaking raw errors:

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

Raw stack traces, provider-specific details, and network errors are never exposed in challenge content.

---

## 6. Pipeline Integration Flow

The complete integration pipeline connects untrusted providers, validators, retry orchestration, and deterministic fallback:

```
Generator / Provider Output
             │
             ▼
   Common Output Validator  ──(Fail)──► Attempt Counter < Max? ──(Yes)──► Bounded Retry
             │ (Pass)                                             ──(No)──►
             ▼                                                               │
   Domain-Specific Validator ──(Fail)──► Attempt Counter < Max? ──(Yes)──►   │
             │ (Pass)                                             ──(No)──►   │
             ▼                                                               │
   Success: Validated Content                                                ▼
                                                                Deterministic Fallback
                                                                (Preserves Type & Diff)
```

The resulting `OrchestratedGenerationResult` contains full telemetry (`is_fallback`, `attempts_used`, `report`, `fallback_resolution`), ensuring downstream alarm session execution has complete visibility into generation origin.
