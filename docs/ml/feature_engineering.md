# SmartWake AI — ML Feature Engineering & Data Preparation

This document specifies the architecture, feature definitions, calculation formulas, data-leakage safeguards, and dataset construction pipeline for Phase 3.0 of SmartWake AI.

---

## 1. Purpose

The goal of the ML Data Preparation and Feature Engineering layer is to extract rich, informative behavioral and contextual signals from user wake cycles. Later stages in Phase 3 (Adaptive Difficulty, Dynamic Parameter Adaptation) use this foundation to train models and make runtime personalization decisions.

### Core Product Constraints
- **User Agency**: The user always selects the challenge type (`dance`, `math`, `memory`, `tongue_twister`, `push_ups`) when creating an alarm.
- **Scope of ML**: ML models adapt the difficulty (`easy`, `medium`, `hard`) and intra-challenge parameters (e.g. sentence length, repetition goals) *within* the user's selected challenge type. ML **never** alters the user's selected challenge type or alarm scheduled time.

---

## 2. Data Sources

All features are derived from the following persistent database entities:

| Database Entity | Telemetry Captured |
|---|---|
| `users` | User identifier and account creation metadata. |
| `alarms` | Scheduled time (`HH:MM`), recurrence pattern (`days_of_week`), user-selected challenge type, baseline difficulty preference (`adaptive`, `easy`, `medium`, `hard`). |
| `wake_sessions` | Lifecycle state (`ringing`, `snoozed`, `in_challenge`, `completed`, `abandoned`), `initial_ring_time`, `scheduled_time`, `total_snooze_count`, `total_wake_delay_seconds`. |
| `snooze_events` | Granular per-snooze telemetry: `snooze_number`, `snoozed_at`, `ring_resumed_at`, `snooze_duration_minutes`. |
| `challenge_attempts` | Prior execution metrics: `challenge_type`, `difficulty_level`, `attempt_number`, `started_at`, `completed_at`, `duration_seconds`, `is_successful`, `verification_score`. |

---

## 3. Canonical Feature Schema

The feature schema comprises **28 input features** organized into 5 distinct categories, plus isolated supervised training targets and metadata columns.

### Category 1: USER_HISTORY (10 Features)
Captures global behavioral trends across all historical wake sessions strictly prior to the current session:
1. `user_total_wake_sessions` (`int`): Count of completed or abandoned wake sessions before this session.
2. `user_successful_wake_sessions` (`int`): Count of prior sessions with `status == "completed"`.
3. `user_failed_wake_sessions` (`int`): Count of prior sessions with `status == "abandoned"`.
4. `user_historical_success_rate` (`float`): Ratio of successful to total prior sessions (`[0.0, 1.0]`).
5. `user_avg_completion_time_seconds` (`float`): Average duration (seconds) of successful attempts across all challenge types.
6. `user_avg_attempts_per_session` (`float`): Ratio of total historical attempts to total wake sessions.
7. `user_avg_snooze_count` (`float`): Mean snoozes per prior wake session.
8. `user_total_snooze_count` (`int`): Cumulative total snoozes pressed across all prior wake sessions.
9. `user_recent_snooze_count` (`int`): Total snoozes pressed in the most recent completed wake session.
10. `user_recent_challenge_success_rate` (`float`): Success rate over the last 5 completed attempts.

### Category 2: CHALLENGE_HISTORY (11 Features)
Captures historical performance isolated strictly to the user's selected challenge type:
11. `challenge_type_total_attempts` (`int`): Total historical attempts by user for this challenge type.
12. `challenge_type_successful_attempts` (`int`): Successful historical attempts for this challenge type.
13. `challenge_type_success_rate` (`float`): Ratio of successful to total attempts for this challenge type.
14. `challenge_type_avg_completion_time` (`float`): Average completion duration for successful attempts of this type.
15. `challenge_type_avg_attempts_per_session` (`float`): Average attempts needed when this challenge type was played.
16. `challenge_type_easy_attempts` (`int`): Historical attempts at 'easy' difficulty.
17. `challenge_type_easy_success_rate` (`float`): Historical success rate at 'easy' difficulty.
18. `challenge_type_medium_attempts` (`int`): Historical attempts at 'medium' difficulty.
19. `challenge_type_medium_success_rate` (`float`): Historical success rate at 'medium' difficulty.
20. `challenge_type_hard_attempts` (`int`): Historical attempts at 'hard' difficulty.
21. `challenge_type_hard_success_rate` (`float`): Historical success rate at 'hard' difficulty.

### Category 3: SNOOZE_HISTORY (3 Features)
Measures active sleep inertia and fatigue accumulated in the current session *before* the challenge begins:
22. `current_session_snooze_count` (`int`): Snoozes pressed in this session prior to attempt reference time.
23. `current_session_snooze_duration_minutes` (`int`): Cumulative snooze duration (minutes) in this session before attempt.
24. `current_session_wake_delay_seconds` (`float`): Elapsed seconds from `initial_ring_time` to attempt start.

### Category 4: ALARM_CONTEXT (5 Features)
Captures temporal rhythms and historical sleep patterns:
25. `alarm_scheduled_hour` (`int`): Scheduled alarm hour (0–23).
26. `alarm_scheduled_minute` (`int`): Scheduled alarm minute (0–59).
27. `alarm_day_of_week` (`int`): Day of week (0=Monday, 6=Sunday).
28. `alarm_is_weekend` (`int`): 1 if Saturday or Sunday, else 0.
29. `historical_snooze_avg_around_alarm_time` (`float`): Mean snoozes for prior sessions scheduled within ±1 hour.

### Category 5: CURRENT_CONTEXT (3 Features)
User configuration parameters for the current session:
30. `selected_challenge_type` (`str`): The user-chosen challenge type (`"dance"`, `"math"`, `"memory"`, `"tongue_twister"`, `"push_ups"`).
31. `user_selected_difficulty` (`str`): Base difficulty preference (`"adaptive"`, `"easy"`, `"medium"`, `"hard"`).
32. `is_adaptive_preference` (`int`): 1 if difficulty is `"adaptive"`, else 0.

### Supervised Target Labels (Decoupled from Features)
These fields are stored exclusively as training targets (`y`), never as input features:
- `target_is_successful`: 1 (passed) or 0 (failed).
- `target_duration_seconds`: Attempt completion duration.
- `target_verification_score`: Automated accuracy/confidence score (0.0 to 1.0).
- `target_attempt_number`: Attempt sequence within session.

---

## 4. Data-Leakage Prevention Guarantees

Data leakage occurs when target or post-event information is inadvertently included in model training features, producing artificially high accuracy in testing that fails in production.

SmartWake AI prevents data leakage through strict design rules:

1. **Temporal Boundary Enforcement**:
   - Queries for prior wake sessions strictly filter for sessions whose `scheduled_time < wake_session.scheduled_time` and terminal statuses (`completed`, `abandoned`).
   - Intra-session prior attempts are strictly restricted to `attempt_number < current_attempt_number`.
2. **Post-Event Isolation**:
   - The outcome attributes of the current attempt (`is_successful`, `completed_at`, `duration_seconds`, `verification_result`, `verification_score`, `failure_reason`) are NEVER read or aggregated into input features.
3. **Automated Verification**:
   - Regression tests verify that modifying or corrupting an attempt's outcome fields produces a bitwise identical feature vector.

---

## 5. Cold-Start and Empty-Database Handling

When a new user registers or the system runs against a fresh database:
- Zero records exist in `challenge_attempts` and `wake_sessions`.
- The dataset builder (`build_challenge_feature_dataframe`) gracefully returns an empty DataFrame containing all canonical columns with predefined schemas.
- Feature extraction functions use `_safe_divide()` to guard against division-by-zero, returning neutral default baselines:
  - Counts default to `0`.
  - Rates default to `0.0`.
  - Durations default to `0.0`.
  - No exceptions or crashes are raised.

---

## 6. Synthetic Development Dataset

To enable offline ML model development and validation without polluting the production database:
- **Location**: `ml/data/raw/synthetic_challenge_attempts.json` and `ml/data/raw/synthetic_challenge_features.csv`.
- **Generator**: `ml/synthetic_generator.py`.
- **Reproducibility**: Built with a fixed seed (`seed=42`) using pseudo-random generators.
- **Coverage**: Simulates 10 synthetic user archetypes over 30 days covering all 5 challenge types and difficulty tiers.
- **Safety**: Pure file-system output. It does **not** connect to or write records to `smartwake.db`.
