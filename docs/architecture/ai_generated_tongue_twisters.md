# AI-Generated Tongue Twister Challenges Specification

**Phase 4.4 — AI-Generated Tongue Twister Challenges**  
**SmartWake AI** — Personalized Adaptive Smart Alarm Clock  
**Package:** `backend.app.services.genai`

---

## 1. Executive Summary & Purpose

Phase 4.4 establishes the foundational architecture for **AI-Generated Tongue Twister Challenges** in SmartWake AI.

Tongue twisters stimulate cognitive and somatic wakefulness by challenging vocal enunciation and articulatory motor coordination. Under SmartWake AI's **zero-trust AI architecture**, Generative AI models are untrusted content generators:
- **Authoritative Boundaries:** The application is the sole authority for challenge type, concrete difficulty (determined by Phase 3 ML), language (`en`), repetition policy/bounds, and speaking duration bounds.
- **Passage Generation Focus:** The primary role of GenAI is to produce creative, alliterative, and phonetically challenging sentences or rhymes.
- **Targeted Non-Numeric Rules:** Digit characters (`0–9`) and arithmetic expressions are strictly forbidden in passages. Numbers must be spelled out (e.g. `"thirty-three"`).
- **Lightweight Orthographic Sound-Pattern Heuristic:** Sound repetition is verified using a pure-Python orthographic consonant onset-pattern heuristic (identifying repeated initial clusters like `sh`, `ch`, `th`, `fl`, `p`, `b`). It explicitly does **not** claim true phoneme-level pronunciation analysis and introduces **zero new dependencies**.
- **Deterministic Validation & Zero Silent Clamping:** If the provider returns repetition or duration values outside the authoritative difficulty tier, the response is deterministically **rejected** (no silent repair).
- **Untrusted LLM Answers:** If the LLM proposes an answer that conflicts with the Python-derived canonical answer, the challenge is rejected.

```
Authoritative Challenge Type: "tongue_twister"
+
Authoritative Concrete Difficulty: "easy" | "medium" | "hard" (from Phase 3 ML)
+
Safe Generation Context: SafePersonalizationContext (sanitized, zero PII)
+
Tongue Twister Constraints: TongueTwisterGenerationConstraints (word count, repetition, duration limits)
       ↓
TongueTwisterPromptBuilder (Structured provider prompt with JSON schema)
       ↓
GenAIService / Active Provider (MockGenAIProvider in tests)
       ↓
TongueTwisterChallengePayload (Strict schema, extra="forbid", strict=True)
       ↓
TongueTwisterAnswerValidator (Text structure, sound-pattern heuristic, non-numeric check, answer derivation)
       ↓
ChallengeContentValidator (Framework validation: immutability, payload size, forbidden terms)
       ↓
ValidatedChallengeContent (Internal validated domain model with authoritative expected_answer)
```

---

## 2. Phase 4.4 Architectural Boundaries

1. **Tongue Twister Only:** Implements GenAI tongue twister generation only. Dance and Push-ups remain deferred.
2. **Procedural Generators Preserved:** Existing Phase 2.7.3 procedural generators (`_generate_tongue_twister`, etc.) in `challenge_generation_service.py` remain **unmodified**.
3. **Completion Verification Preserved:** Existing Phase 2.8 verification engine (`verify_tongue_twister`) in `challenge_verification_service.py` remains **unmodified**. Phase 4.4 produces canonical string answers compatible with its existing transcript verification contract.
4. **Runtime Execution Preserved:** `ChallengeExecutionService` and wake session alarm lifecycles are **unmodified**.
5. **Runtime Contract Decoupling:** `RuntimeChallengeResponse` is **unmodified** (uses `generated_content`). Future Phase 4.7 will map `ValidatedChallengeContent.content_payload` into `RuntimeChallengeResponse.generated_content`.
6. **Zero Database Impact:** Zero ORM models, zero migrations, zero writes to `smartwake.db`.
7. **Zero New Dependencies:** Zero packages added to `requirements.txt`.

---

## 3. Separation of Responsibilities Across Phases

| Phase / Engine | Core Question Answered | Authoritative Output |
|---|---|---|
| **Phase 3 ML (`AdaptiveDecisionEngine`)** | *"How difficult should the tongue twister challenge be?"* | Concrete difficulty: `easy`, `medium`, or `hard`. |
| **Phase 4.4 GenAI (`TongueTwisterChallengeGenerator`)** | *"What tongue twister content should be generated at that already-selected difficulty?"* | `ValidatedChallengeContent` with independently derived `expected_answer`. |
| **Phase 2.8 Verification (`verify_tongue_twister`)** | *"Did the user clearly articulate it during the alarm?"* | `ChallengeVerificationResult` (`is_successful`, score). |

---

## 4. Supported Language Strategy

- **Locked to English (`"en"`)**: Phase 4.4 explicitly supports English only.
- **Deterministic Rejection**: Any request specifying another language code is deterministically rejected with `TongueTwisterEvaluationError`.
- **Zero Silent Fallback**: The pipeline will never silently substitute English when another language was requested.

---

## 5. Difficulty Constraints & Authoritative Boundaries

| Parameter | Easy Tier | Medium Tier | Hard Tier |
| :--- | :---: | :---: | :---: |
| **Allowed Language** | `en` | `en` | `en` |
| **Word Count Range** | 6 – 12 words (default: 8) | 12 – 20 words (default: 15) | 20 – 35 words (default: 25) |
| **Authoritative Repetitions** | 1 – 2 reps (default: 2) | 2 – 3 reps (default: 2) | 3 – 4 reps (default: 3) |
| **Authoritative Speaking Time**| 15 – 20s (default: 15s) | 20 – 35s (default: 25s) | 35 – 60s (default: 45s) |
| **Degeneracy Safeguard** | Unique word ratio $\ge 0.35$ | Unique word ratio $\ge 0.40$ | Unique word ratio $\ge 0.45$ |
| **Orthographic Sound Pattern** | $\ge 1$ cluster/onset repeated $\ge 3\times$ | $\ge 1$ onset $\ge 4\times$ (or 2 onsets $\ge 3\times$) | $\ge 1$ onset $\ge 5\times$ (or 2 onsets $\ge 4\times$) |

---

## 6. Trust Boundary & Validation Rules

### 6.1 Application-Authoritative Controls
- `challenge_type`: Locked to `"tongue_twister"`.
- `difficulty_level`: Locked to concrete tier from caller (`easy`, `medium`, `hard`).
- `language`: Locked to `"en"`.
- `target_repetitions`: Application tier determines allowed range. If provided by LLM, must be inside tier bounds; otherwise rejected. If omitted, default tier value is assigned.
- `speaking_duration_seconds`: Application tier determines allowed range. If provided by LLM, must be inside tier bounds; otherwise rejected. If omitted, default tier value is assigned.

### 6.2 Passage Validation
- **No Digits in Passage:** Digits `0–9` are rejected (`\d`). Spelled-out numbers (e.g. `"thirty-three"`) are permitted.
- **Forbidden Concepts:** Scans for context-aware forbidden concepts (`"guess the number"`, `"pin code"`, `"otp"`, `"passcode"`). Ordinary words like `"code"` or `"guess"` in non-numeric contexts are not blanket-rejected.
- **Natural Punctuation:** Standard punctuation is allowed. Repeated abusive punctuation (`???`, `!!!`) is rejected.
- **Degeneracy Safeguard:** Rejects pathological single-word loops (e.g. `"test test test test test"`).
- **Lightweight Orthographic Sound-Pattern Heuristic:** Analyzes consonant onset clusters (`sh`, `ch`, `th`, `fl`, `p`, `b`, etc.) to verify sound repetition. It does **not** claim to be a phoneme classifier.
- **Anti-Prompt Injection:** Rejects meta-instructions (`"ignore previous instructions"`, `"change challenge to math"`).

---

## 7. Canonical Answer Derivation

1. **Authoritative Expected Answer:**
   `canonical_expected_answer = " ".join(passage.strip().split())`
   (trimmed, whitespace-collapsed string).
2. **Display Preservation:**
   Original `passage` with exact casing and natural punctuation is preserved in `content_payload["passage"]` for UI display.
3. **Proposed Answer Consistency Check:**
   If `proposed_answer` is supplied, it is normalized and compared against the derived answer. Any mismatch triggers `TongueTwisterEvaluationError`. If omitted, generation succeeds with the application-derived answer.

---

## 8. Personalization & Duration Scaling

`TongueTwisterPromptBuilder` consumes `SafePersonalizationContext`:
- **Bounded Duration Scaling:** `desired_duration_seconds` can only calibrate `target_word_count`, `target_repetitions`, and `speaking_duration_seconds` **within the already-authoritative Phase 3 difficulty bounds**.
- **No Tier Escalation:** It must NEVER escalate or downgrade the concrete difficulty tier.
- **Identity Privacy Guarantee:** Prompts never reference `user_id`, `email`, `session_id`, `alarm_id`, or tokens.

---

## 9. Exception Hierarchy

```
SmartWakeException
└── GenAIError
    ├── GenAIValidationError
    │   └── ChallengeContentValidationError
    │       ├── MathEvaluationError (Phase 4.2)
    │       ├── MemoryEvaluationError (Phase 4.3)
    │       └── TongueTwisterEvaluationError (Phase 4.4: text bounds, sound-pattern heuristic, digits, proposed answer mismatch)
    │
    ├── MathChallengeGenerationError (Phase 4.2)
    ├── MemoryChallengeGenerationError (Phase 4.3)
    └── TongueTwisterChallengeGenerationError (Phase 4.4: pipeline coordination, provider dispatch error)
```

---

## 10. Future Phase 4.7 Runtime Adapter Roadmap

In Phase 4.4:
- Output: `ValidatedChallengeContent(challenge_type="tongue_twister", content_payload={...}, expected_answer=...)`.

In Phase 4.7:
- An adapter will translate:
  `ValidatedChallengeContent.content_payload` → adapter → `RuntimeChallengeResponse.generated_content`.
- The existing runtime generator (`_generate_tongue_twister`) and `RuntimeChallengeResponse` remain unmodified.
