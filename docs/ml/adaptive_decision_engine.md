# Adaptive Decision Engine (Phase 3.4)

## Overview & Purpose

The **Adaptive Decision Engine** (`AdaptiveDecisionEngine`) acts as the authoritative runtime decision boundary between:
1. **PersonalizationEngine** (Phase 3.3 difficulty resolution policies: ColdStartRouter, SafetyGuardrails, ModelInferenceManager), and
2. **Runtime Challenge Generation & Execution** (Phase 2.7–2.9 challenge generation and attempt tracking).

It ensures that candidate personalization policies are validated, safety constraints and operational guardrails are upheld, and product invariants are strictly enforced before any challenge is instantiated and served to the user.

---

## Separation of Concerns: PersonalizationEngine vs. AdaptiveDecisionEngine

| Responsibility | PersonalizationEngine (Phase 3.3) | AdaptiveDecisionEngine (Phase 3.4) |
| :--- | :--- | :--- |
| **Role** | Core intelligence & candidate resolution | Runtime decision boundary & validator |
| **Input Context** | User session history, snoozes, feature vector | Session context, database state, user choice |
| **Precedence Policy** | Evaluates rules, ML, and guardrails | Enforces user sovereignty and boundary validation |
| **Output** | `PersonalizationDecision` (candidate difficulty) | `AdaptiveChallengeDecision` (authoritative final decision) |
| **Execution Context** | Service-level ML & rule evaluation | Runtime execution orchestrator before `generate_challenge` |
| **Failure Defense** | Safe fallback for low confidence / missing telemetry | Rejects malformed decisions, invalid types, or mutated categories |

---

## Runtime Decision Flow

```
                WakeSession (active)
                        ↓
            User-Selected Challenge Type
          ('dance', 'math', 'memory',
         'tongue_twister', 'push_ups')
                        ↓
             Difficulty Preference
        ('easy', 'medium', 'hard', 'adaptive')
                        ↓
             AdaptiveDecisionEngine
            ┌───────────┴───────────┐
            │                       │
      [Fixed Choice]           [Adaptive]
     ('easy'|'med'|'hard')          │
            │              PersonalizationEngine
            │             (ColdStartRouter / ML /
            │                SafetyGuardrails)
            │                       │
            │             Validate Candidate
            │             (Category & Tier Check)
            └───────────┬───────────┘
                        ↓
            AdaptiveChallengeDecision
           - authoritative final_difficulty
           - preserved challenge_type
           - decision_source & rationale
           - model_confidence & snapshot
                        ↓
            Runtime Challenge Generation
            (generate_challenge: type + diff)
                        ↓
                 ChallengeAttempt
```

---

## Fixed vs. Adaptive Behavior

### 1. Fixed Difficulty Preference
- **Precedence**: Absolute user sovereignty.
- **Rule**: If the user selects `'easy'`, final difficulty **MUST** be `'easy'`. If `'medium'`, final difficulty **MUST** be `'medium'`. If `'hard'`, final difficulty **MUST** be `'hard'`.
- **Bypass**: ML model inference and adaptive safety guardrails (such as the snooze-count sleep inertia floor or previous-session step-shift clamp) are **completely bypassed**.
- **Decision Source**: `DecisionSource.USER_FIXED` (`"user_fixed"`).

### 2. Adaptive Difficulty Preference
- **Resolution**: Evaluated dynamically based on user lifecycle:
  - **Stage 0 (0–3 sessions)**: Task-demand and snooze heuristics (no ML). High-cognitive tasks (`math`, `memory`) default to `easy`; physical tasks default to `medium`. Snoozes >= 2 downgrade to `easy`.
  - **Stage 1 (4–7 sessions)**: Rolling performance rules (no ML). Recent failure or slow completion (> 40s) sets `easy`. 100% success and fast completion (< 15s) promotes baseline by +1 level.
  - **Stage 2 (8+ sessions)**: Baseline Logistic Regression model inference (`ModelInferenceManager`).
- **Confidence Threshold**:
  - If top-class probability $\ge 0.60$: candidate is accepted (`DecisionSource.ML_ADAPTIVE`).
  - If top-class probability $< 0.60$: safely falls back to Stage 1 contextual heuristics without fabricating telemetry (`DecisionSource.FALLBACK_SAFE`).
- **Safety Guardrails**:
  - **Step-Shift Clamp**: Maximum $\pm 1$ difficulty tier shift relative to `previous_difficulty`.
  - **Sleep Inertia Floor**: If current session snooze count $\ge 3$, difficulty is capped at `'medium'` (never `'hard'`).

---

## Core Product Invariants

1. **User Chooses Challenge Type**:
   - Supported canonical types: `dance`, `math`, `memory`, `tongue_twister`, `push_ups`.
   - ML and the Decision Engine **MUST NEVER** alter or replace the user's chosen task type.
   - Forbidden types (`number_guessing`, `guess_number`, `numeric_memory`) are strictly rejected.

2. **User Chooses Alarm Time**:
   - Alarm scheduled time and wake session ring times are immutable at runtime. ML **MUST NEVER** alter alarm times.

3. **Zero Post-Challenge Leakage**:
   - Features and telemetry are computed strictly **prior** to the current attempt (`ref_time = now_utc()`).
   - Post-challenge outcome fields (`target_is_successful`, `target_duration_seconds`, `target_verification_score`, `completed_at`) of the current attempt are never used to determine the same attempt's difficulty.

4. **Zero Telemetry Fabrication**:
   - No synthetic dataset generation or mock values at runtime. Missing historical telemetry safely triggers Stage 0/1 heuristic fallback.
