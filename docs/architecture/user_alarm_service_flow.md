# SmartWake AI — User & Alarm Configuration Flow

This document details the backend service layer architecture for configuring users and their scheduled alarms in **SmartWake AI**.

---

## 1. Cardinal Product Rule

```
┌────────────────────────────────────────────────────────┐
│                   USER CONFIGURATION                   │
│                     (User Controls)                    │
├────────────────────────────────────────────────────────┤
│  1. Scheduled Alarm Time (e.g., '07:00 AM')            │
│  2. Wake-up Challenge Type:                            │
│     - Dance                                            │
│     - Math                                             │
│     - Memory (pattern/sequence recall, not guessing)   │
│     - Tongue Twister                                   │
│     - Push-ups                                         │
│  3. Baseline Difficulty Preference:                    │
│     - 'adaptive' (ML tunes challenge parameters)       │
│     - 'easy', 'medium', 'hard' (manual baseline)       │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│                      ML ADAPTATION                     │
│                (Future Personalization)                │
├────────────────────────────────────────────────────────┤
│  - Tunes difficulty parameters (word count, reps)      │
│  - Generates personalized content within selected type │
│  - Calibrates verification thresholds                  │
│                                                        │
│  ML DOES NOT:                                          │
│  ❌ Choose the task type                               │
│  ❌ Change the user's requested alarm time             │
└────────────────────────────────────────────────────────┘
```

---

## 2. Service Layer Functions

### 2.1 User Service (`backend/app/services/user_service.py`)
* **`create_user(db, username, email=None, timezone="UTC")`**:
  * Inserts and returns a new `User` record.
  * Ensures username uniqueness (raises `UserAlreadyExistsError` on conflict).
  * Manages database transactions with automatic rollback on error.
* **`get_user_by_id(db, user_id)`**: Retrieves user by primary key.
* **`get_user_by_username(db, username)`**: Retrieves user by unique username.

### 2.2 Alarm Service (`backend/app/services/alarm_service.py`)
* **`create_alarm(db, user_id, time, selected_challenge_type, difficulty_preference="adaptive", ...)`**:
  * Validates that the referenced user exists (raises `UserNotFoundError`).
  * Validates that `time` matches 24-hour format `"HH:MM"` (`00:00` to `23:59`).
  * Validates that `selected_challenge_type` is one of: `'dance'`, `'math'`, `'memory'`, `'tongue_twister'`, `'push_ups'`.
  * Validates that `difficulty_preference` is one of: `'easy'`, `'medium'`, `'hard'`, `'adaptive'`.
  * Persists the record transactionally with automatic rollback on failure.
* **`get_alarm_by_id(db, alarm_id)`**: Retrieves a single alarm by primary key.
* **`get_alarms_by_user(db, user_id)`**: Retrieves all alarms configured by a specific user.

---

## 3. Validation Rules

| Field | Validation Rule | Exception Raised |
| :--- | :--- | :--- |
| `user_id` | Must exist in `users` table | `UserNotFoundError` |
| `time` | Must match regex `^([01]\d\|2[0-3]):([0-5]\d)$` | `InvalidAlarmTimeError` |
| `selected_challenge_type` | Must be in `{'dance', 'math', 'memory', 'tongue_twister', 'push_ups'}` | `InvalidChallengeTypeError` |
| `difficulty_preference` | Must be in `{'easy', 'medium', 'hard', 'adaptive'}` | `InvalidDifficultyError` |
| `username` | Cannot be empty or duplicate | `ValueError` / `UserAlreadyExistsError` |

---

## 4. Test Isolation Strategy

The test suite at `backend/tests/test_user_alarm_service.py` runs against an in-memory SQLite database (`sqlite:///:memory:` with `StaticPool`). This guarantees:
1. Fast, self-contained unit/integration test execution.
2. Zero pollution of the development database file (`smartwake.db`).
