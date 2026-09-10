# Generative AI Architecture Specification

**Phase 4.0 — GenAI Architecture & Provider Foundation**  
**SmartWake AI** — Personalized Adaptive Smart Alarm Clock

---

## 1. Executive Summary

Generative AI (Phase 4) enhances the SmartWake AI alarm system by synthesizing fresh, varied, and contextual wake-up challenge content.

Phase 4 introduces Generative AI with strict separation of concerns and operational guardrails:
- **Phase 3 ML (`AdaptiveDecisionEngine`):** Decides *"How difficult should the challenge be?"* (outputs a concrete difficulty: `easy`, `medium`, `hard`).
- **Phase 4 GenAI (`GenAIService`):** Decides *"What fresh challenge content should be generated at that selected type and concrete difficulty?"*
- **Phase 2.8 Verification (`verify_challenge`):** Decides *"Did the user actually complete the challenge?"*

```
AdaptiveDecisionEngine (Phase 3)
           ↓
[challenge_type + concrete difficulty ('easy' / 'medium' / 'hard')]
           ↓
GenAIService (Phase 4)
           ↓
Provider Abstraction (BaseGenAIProvider)
           ↓
┌──────────────────────┬──────────────────────┐
│  MockGenAIProvider   │  GeminiProvider      │
│  (Contract/Offline)  │  (HTTP REST Adapter) │
└──────────────────────┴──────────────────────┘
           ↓
Pydantic Structured Validation (GenAIGenerationResponse)
           ↓
Runtime Challenge Content (Phase 2.7 Runtime Format)
           ↓
Phase 2.8 Verification Engine
```

---

## 2. Phase 4 Roadmap Boundaries

To ensure systematic, robust implementation, Phase 4 is partitioned into nine focused sub-phases:

| Sub-Phase | Title | Focus & Scope |
|---|---|---|
| **4.0** | **GenAI Architecture & Provider Foundation** | **Current Scope**: Abstract provider contracts, configuration, contract-level mock provider, model-agnostic Gemini adapter, factory, and error hierarchy. |
| **4.1** | Personalized Challenge Content Framework | Prompt templating engine, token budgeting, and formatting abstractions across task categories. |
| **4.2** | AI-Generated Math Challenges | Dynamic arithmetic synthesis, word problems, and verified solutions. |
| **4.3** | AI-Generated Memory Challenges | Spatial layouts, visual sequences, and non-number-guessing pattern synthesis. |
| **4.4** | AI-Generated Tongue Twisters | Phonetically challenging sentences scaled by alliterative complexity and word count. |
| **4.5** | AI-Powered Challenge Personalization | Context-aware prompt injection using safe user history. |
| **4.6** | GenAI Safety, Validation & Fallback | Structured schema validation, latency budgets, and seamless fallback to procedural catalog. |
| **4.7** | GenAI Runtime Integration | Hooking GenAI into `ChallengeExecutionService` and wake session attempt lifecycle. |
| **4.8** | Phase 4 Testing, Documentation & Final Audit | End-to-end load tests, architectural audit, and final sign-off. |

---

## 3. User Sovereignty & Safety Guarantees

Phase 4 strictly upholds all foundational invariants established in Phases 1–3:
1. **User-Selected Challenge Type is Immutable:** GenAI NEVER selects, suggests, or changes the user's selected challenge type (`math`, `memory`, `dance`, `tongue_twister`, `push_ups`).
2. **Alarm Scheduled Time is Immutable:** GenAI has zero interaction with scheduling or alarm times.
3. **Fixed Difficulty Precedence:** When a user specifies fixed difficulty (`easy`, `medium`, `hard`), it enters GenAI directly without modification.
4. **Concrete Difficulty Only:** GenAI never receives or outputs ambiguous tiers like `adaptive`.
5. **No Verification Bypass:** GenAI produces challenge content; it NEVER determines whether a user passed. Phase 2.8 deterministic verification remains the sole authority.
6. **Strict Non-Number Guessing Rule:** Memory challenges strictly evaluate visual and spatial recall; number guessing is rejected at the schema level.
7. **No Single Point of Failure:** GenAI is an enhancement. If an external API is down, rate-limited, or times out, the system immediately falls back to procedural templates without interrupting the alarm.

---

## 4. Provider Abstraction & Strategy Pattern

The provider layer (`backend/app/services/genai/`) abstracts the external model API:

### 4.1 Base Provider Contract (`BaseGenAIProvider`)
Defines the required interface:
- `generate(request: GenAIContentRequest) -> GenAIGenerationResponse`: Structured generation.
- `check_health() -> GenAIProviderHealth`: Readiness check.
- Properties: `provider_name`, `model_name`, `timeout_seconds`, `temperature`.

### 4.2 Mock Provider (`MockGenAIProvider`)
- Operating strictly at the **contract level**, the mock provider does not implement challenge-specific math, memory, or tongue twister logic (which belongs to Phase 4.1–4.5).
- Returns deterministic structured responses confirming schema serialization, call tracking, and latency measurement.
- Used for all automated unit and integration tests and offline development.

### 4.3 Gemini Provider (`GeminiProvider`)
- **Model-Agnostic Design:** Accepts any configured model identifier via `GENAI_MODEL` without hardcoded model locking.
- **REST via Standard Library:** Uses standard HTTP requests without heavy cloud SDK dependencies.
- **Error Mapping:** Converts HTTP status codes into typed domain exceptions (`GenAIConfigurationError`, `GenAIRateLimitError`, `GenAIProviderUnavailableError`, `GenAITimeoutError`).

### 4.4 Provider Factory (`get_genai_provider`)
- Instantiates the configured provider (`mock` or `gemini`) from application settings.
- Supports runtime provider registration via `register_provider(name, cls)`.

---

## 5. Configuration & Secret Management

Configuration is handled centrally in `backend/app/core/config.py`:

| Variable | Type | Default | Description |
|---|---|---|---|
| `GENAI_ENABLED` | `bool` | `False` | Master switch. Alarms function normally when disabled. |
| `GENAI_PROVIDER` | `str` | `"mock"` | Selected provider (`mock`, `gemini`). |
| `GENAI_API_KEY` | `Optional[str]` | `None` | Read exclusively from environment. Never committed. |
| `GENAI_MODEL` | `str` | `"gemini-2.0-flash"` | Dynamic model identifier. |
| `GENAI_TIMEOUT_SECONDS` | `float` | `5.0` | Timeout threshold to prevent alarm delays. |
| `GENAI_MAX_RETRIES` | `int` | `1` | Retry limit before triggering fallback. |
| `GENAI_TEMPERATURE` | `float` | `0.7` | Sampling temperature for variety. |

### Secret Masking
`settings.masked_genai_api_key` ensures credentials are never logged or exposed in health check endpoints (e.g. `AIza...****` or `not_set`).

---

## 6. Error Hierarchy

All GenAI exceptions inherit from `SmartWakeException` in `backend/app/core/exceptions.py`:

```
SmartWakeException
       └── GenAIError
              ├── GenAIConfigurationError
              ├── GenAIProviderUnavailableError
              ├── GenAITimeoutError
              ├── GenAIRateLimitError
              └── GenAIValidationError
```

---

## 7. Zero Database & Dependency Impact

- **Database:** Zero new tables, columns, or migrations. `smartwake.db` is completely untouched.
- **Dependencies:** Zero new third-party packages installed in `requirements.txt`.
