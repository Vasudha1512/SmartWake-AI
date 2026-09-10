# Cold-Start & Fallback Strategy (Phase 3.5)

## Overview & System Objective

The **Cold-Start and Fallback Strategy** (`Phase 3.5`) provides a deterministic, reliable, and fault-tolerant difficulty resolution architecture for SmartWake AI. It ensures the smart alarm clock operates seamlessly across all stages of the user lifecycle—from brand new users with zero history to active long-term users encountering infrastructure, database, or ML inference anomalies.

### Core Guarantee
Under no circumstances will a wake-up alarm fail to present a challenge or crash the user experience due to:
- Missing or sparse historical records
- Incomplete or partial session telemetry
- Model artifact unreachability, corruption, or schema incompatibility
- Low ML classification confidence ($< 0.60$)
- Database latency, connection drops, or runtime exceptions

---

## Architectural Separation: Phase 3.3 vs. Phase 3.5

| Dimension | Phase 3.3: Core Personalization Components | Phase 3.5: System-Level Cold-Start & Fallback Strategy |
| :--- | :--- | :--- |
| **Focus** | Component-level building blocks (`ColdStartRouter`, `SafetyGuardrails`, `ModelInferenceManager`, `PersonalizationEngine`). | End-to-end resilience, deterministic fallback hierarchy, defensive boundaries, and failure diagnostics. |
| **Fallback Policy** | Ad-hoc fallback hooks per component. | **Single authoritative deterministic fallback policy** concentrated in `ColdStartRouter.evaluate_safe_fallback()`. |
| **Telemetry Handling** | Opportunistic telemetry consumption. | Strict categorization into **complete**, **genuinely available partial**, and **unavailable** telemetry with **zero fabrication**. |
| **Failure Modes** | Basic component exceptions. | Explicit handling of 10 ML/infrastructure failure modes with non-penalizing diagnostic auditability. |
| **Safety Guardrails** | Operational clamping rules. | Precise tracking distinguishing unmodified `FALLBACK_SAFE` from `GUARDRAIL_CLAMPED`. |

---

## Formal 7-Level Fallback Hierarchy

When determining challenge difficulty, the system traverses the following strict precedence hierarchy:

```
[Level 1] User-Fixed Preference (easy, medium, hard)
    │   └── Absolute precedence; strictly bypasses ML, fallback, and guardrails
    ▼ (if preference == 'adaptive')
[Level 2] Cold Start Stage 0 (0–3 historical sessions)
    │   └── Deterministic task-demand heuristics & snooze inertia downgrade (no ML)
    ▼ (if 4+ historical sessions)
[Level 3] Cold Start Stage 1 (4–7 historical sessions)
    │   └── Deterministic moving-average rules using recent performance (no ML)
    ▼ (if 8+ historical sessions)
[Level 4] Stage 2 ML Adaptive Decision
    │   └── Baseline difficulty classifier prediction if confidence >= 0.60
    ▼ (if confidence < 0.60)
[Level 5] Low-Confidence Fallback
    │   └── Safest available contextual fallback via ColdStartRouter.evaluate_safe_fallback()
    ▼ (if model file missing, corrupt, metadata invalid, or schema incompatible)
[Level 6] Model Unavailable Fallback
    │   └── Deterministic fallback via ColdStartRouter.evaluate_safe_fallback() + diagnostic error logging
    ▼ (if historical telemetry or feature record is missing)
[Level 7] Incomplete / Infrastructure Telemetry Fallback
        └── Safest baseline fallback via ColdStartRouter.evaluate_safe_fallback() + zero telemetry fabrication
```

---

## Cold-Start Lifecycle Stages

### Stage 0: Pure Heuristics (0–3 Historical Sessions)
New users lack sufficient behavioral history to establish reliable moving averages.
- **Task Demand Baselines**:
  - High-cognitive tasks (`math`, `memory`): **`easy`** (reduces morning cognitive friction and frustration).
  - Physical/speech tasks (`dance`, `tongue_twister`, `push_ups`): **`medium`** (physiologically activates the motor cortex).
- **Snooze Inertia Downgrade**:
  - If `current_session_snooze_count >= 2`: baseline is downgraded toward **`easy`** to prevent alarm abandonment.
  - If `current_session_snooze_count < 2`: baseline remains unaffected.

### Stage 1: Contextual Moving Average Rules (4–7 Historical Sessions)
Intermediate users have established preliminary wake behavior, enabling contextual adjustments without ML inference:
- **Demotion Trigger (Struggle / Sluggishness)**:
  - If `has_recent_failure == True` OR `recent_avg_duration_seconds > 40.0s`: demotes to **`easy`**.
  - Boundary rule: $40.0$s does *not* trigger demotion; $40.1$s *does* trigger demotion.
- **Promotion Trigger (Mastery)**:
  - If `recent_success_rate == 1.0` (100%) AND `recent_avg_duration_seconds < 15.0s`: promotes baseline difficulty by $+1$ level (e.g., `easy` $\to$ `medium`, `medium` $\to$ `hard`).
  - Boundary rule: $15.0$s does *not* trigger promotion; $14.9$s *does* trigger promotion.
- **Balanced Engagement Default**:
  - If neither struggle nor mastery is observed: resolves to **`medium`**.

### Stage 2: ML Baseline Model Inference (8+ Historical Sessions)
Users with 8 or more completed/abandoned sessions enter Stage 2.
- Pre-challenge feature extraction produces the canonical 30 model input features.
- Baseline logistic regression pipeline outputs probability distributions across `easy`, `medium`, and `hard`.

---

## ML Confidence Threshold ($0.60$) & Boundary Semantics

The baseline classifier produces calibrated probability estimates:
- **Confidence $\ge 0.60$ (Accepted)**:
  - The model's top prediction is accepted as the candidate difficulty.
  - Decision source: `ml_adaptive`.
  - The candidate is subsequently evaluated by `SafetyGuardrails`.
- **Confidence $< 0.60$ (Rejected / Fallback)**:
  - The model's prediction is treated as unauthoritative.
  - The decision automatically falls back to `ColdStartRouter.evaluate_safe_fallback()`.
  - Decision source: `fallback_safe` (or `guardrail_clamped` if clamped).
  - Raw prediction and confidence score are retained diagnostically in the decision artifact for auditing.

---

## Authoritative Deterministic Fallback Policy

To prevent divergent runtime behaviors, SmartWake AI enforces **strictly ONE authoritative deterministic fallback-resolution policy**:

```python
ColdStartRouter.evaluate_safe_fallback(
    challenge_type: str,
    baseline_difficulty: Optional[str] = None,
    recent_success_rate: Optional[float] = None,
    recent_avg_duration_seconds: Optional[float] = None,
    has_recent_failure: bool = False,
    current_session_snooze_count: int = 0,
    trigger_reason: Optional[str] = None,
) -> Tuple[str, str]
```

Both `PersonalizationEngine._decide_impl` and the `AdaptiveDecisionEngine` runtime boundary call this exact method. No component is permitted to invent an independent fallback policy.

### Telemetry Categorization & Zero Fabrication

The fallback engine classifies telemetry strictly into three mutually exclusive categories:

1. **Complete Telemetry**:
   - Both `recent_success_rate` and `recent_avg_duration_seconds` are genuinely present.
   - Stage 1 contextual policy is evaluated fully (supporting both demotion and mastery promotion).
2. **Genuinely Available Partial Telemetry**:
   - At least one metric is present (e.g. `has_recent_failure == True` or `recent_avg_duration_seconds > 40.0s`).
   - Demotion rules evaluate safely against available facts.
   - **Zero Fabrication**: If duration is missing, the system *never* assumes $< 15.0$s; if success rate is missing, the system *never* assumes $1.0$. Partial telemetry without complete metrics cannot trigger mastery promotion.
3. **Unavailable Telemetry**:
   - No historical telemetry is available (`recent_success_rate is None and recent_avg_duration_seconds is None and not has_recent_failure`).
   - Falls back to the safest deterministic baseline:
     - If `baseline_difficulty` is present and `current_session_snooze_count < 2`: prefers `baseline_difficulty` if `easy`, else `medium`.
     - If `baseline_difficulty` is absent or `current_session_snooze_count >= 2`: evaluates Stage 0 heuristics (`math`/`memory` $\to$ `easy`, `snooze >= 2` $\to$ `easy`, physical $\to$ `medium`).
   - No metrics are ever synthesized or generated via `synthetic_generator.py` at runtime.

---

## Defensive ML & Infrastructure Failure Handling

The system guarantees robust exception interception across all potential points of failure:

### 1. ML Model Failure Modes
The following exceptions are intercepted in `PersonalizationEngine._decide_impl`:
- `ModelNotFoundError`: Missing `.joblib` file on disk.
- `ModelCorruptError`: Corrupted serialization or missing `predict_proba` method.
- `ModelMetadataError`: Missing, unparseable, or schema-incompatible metadata JSON.
- `IncompatibleFeatureSchemaError`: Missing required feature columns.
- `RuntimeError` / `Exception`: Numerical or execution exceptions during inference.
- Malformed outputs: Predictions outside `['easy', 'medium', 'hard']`.

**Resolution**: Returns a concrete difficulty via `evaluate_safe_fallback()`. The error type and message are recorded in `feature_snapshot["ml_error_type"]` and `decision_rationale`.

### 2. Database & Infrastructure Failures
Database query exceptions or feature extraction errors during `decide_for_session` are intercepted defensively:
- **Diagnostic Preservation**: The exact failure (`infrastructure_error_type`, `infrastructure_error_detail`) is captured in `feature_snapshot` and `decision_rationale`.
- **Non-Penalization**: Infrastructure failure is **never** treated as evidence of poor user performance (`has_recent_failure = False`).
- **Zero Fabrication**: No synthetic telemetry is injected.
- **Graceful Degradation**: Delegates to `ColdStartRouter.evaluate_safe_fallback()` to return a safe concrete difficulty.

---

## SafetyGuardrails Interaction with Fallbacks

When a fallback candidate difficulty is produced, it is evaluated by `SafetyGuardrails.apply_guardrails()`:
1. **Maximum Step Shift**: The candidate cannot jump more than $\pm 1$ tier from `previous_difficulty`.
2. **Sleep Inertia Floor**: If `current_session_snooze_count >= 3`, difficulty is capped at `medium` (never `hard`).

### Decision Source Accuracy
The decision source accurately reflects the runtime resolution:
- **`DecisionSource.FALLBACK_SAFE`**: Fallback policy was invoked, and safety guardrails accepted the candidate without modification.
- **`DecisionSource.GUARDRAIL_CLAMPED`**: Fallback policy was invoked, but a safety guardrail altered the candidate difficulty.

---

## Non-Negotiable Product Invariants

1. **User Sovereignty Over Challenge Type**:
   - The user's selected challenge type (`dance`, `math`, `memory`, `tongue_twister`, `push_ups`) is immutable.
   - ML, cold-start, and fallback logic strictly *never* alter or substitute the challenge type.
2. **User Sovereignty Over Alarm Time**:
   - The scheduled alarm time is strictly *never* altered by personalization or fallback logic.
3. **Fixed Preference Precedence**:
   - User choices of `easy`, `medium`, or `hard` bypass ML, fallback, and guardrails completely (`DecisionSource.USER_FIXED`).
4. **Concrete Difficulty Guarantee**:
   - Final challenge difficulty must strictly be `'easy'`, `'medium'`, or `'hard'`. It is never `'adaptive'`.
5. **Zero Post-Challenge Leakage**:
   - Decisions are strictly formulated using point-in-time observations available *before* the attempt begins ($T_0$).
6. **Forbidden Types Rejection**:
   - Forbidden types (e.g. number guessing for memory) are rejected during context validation.
7. **No Schema or Artifact Mutations**:
   - Runtime fallback operates without modifying SQLite tables, ORM models, or model files.
