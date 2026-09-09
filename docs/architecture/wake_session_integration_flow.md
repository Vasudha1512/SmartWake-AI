# SmartWake AI — Wake Session Integration Flow & Architecture

This document details the integrated backend architecture uniting **Alarm Configuration**, **Scheduler Execution**, **WakeSession Lifecycle**, and **Snooze Tracking** in **SmartWake AI** (Phase 2.6.4).

---

## 1. End-to-End Wake Session Lifecycle

```
┌────────────────────────────────────────────────────────┐
│                   ALARM CONFIGURATION                  │
│                     (User Controls)                    │
├────────────────────────────────────────────────────────┤
│  - Scheduled alarm time (HH:MM)                        │
│  - Recurrence days of week (0=Mon ... 6=Sun)          │
│  - User-selected challenge type                        │
│  - Baseline difficulty preference                      │
│  - User IANA timezone                                  │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│                   SCHEDULER ENGINE                     │
│               (get_due_alarms / process)               │
├────────────────────────────────────────────────────────┤
│  - Converts current UTC to user's local timezone       │
│  - Verifies local weekday and matching HH:MM           │
│  - Computes exact UTC occurrence timestamp             │
│  - Enforces occurrence idempotency (no duplicates)     │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│                  WAKE SESSION CREATED                  │
│                  (status = 'ringing')                  │
├────────────────────────────────────────────────────────┤
│  - Exactly ONE WakeSession per alarm occurrence        │
│  - Initial status: 'ringing'                           │
│  - scheduled_time: exact occurrence UTC timestamp      │
│  - total_snooze_count: 0                               │
└───────────────────────────┬────────────────────────────┘
                            │
        ┌───────────────────┴───────────────────┐
        │ User requests snooze                  │ User begins challenge
        ▼                                       ▼
┌───────────────────────────────┐     ┌───────────────────────────────┐
│         SNOOZE EVENT          │     │        CHALLENGE PHASE        │
│      (Behavioral Telemetry)   │     │    (Future Phase 2.7+)        │
├───────────────────────────────┤     ├───────────────────────────────┤
│  - Creates child SnoozeEvent  │     │  - Transitions to             │
│  - total_snooze_count += 1    │     │    'in_challenge'             │
│  - Status: 'snoozed'          │     │  - Challenge generated        │
│  - Same WakeSession retained  │     │  - Verification evaluated     │
└───────────────┬───────────────┘     └───────────────┬───────────────┘
                │                                     │
                ▼                                     ▼
┌───────────────────────────────┐     ┌───────────────────────────────┐
│        RESUME RINGING         │     │           TERMINAL            │
│   (PATCH /{id}/resume)        │     │    ('completed'/'abandoned')  │
├───────────────────────────────┤     ├───────────────────────────────┤
│  - Status: 'ringing'          │     │  - Challenge verified         │
│  - ring_resumed_at recorded   │     │  - dismissed_time recorded    │
│  - Alarm can be snoozed again │     │  - total_wake_delay calculated│
│    or transitioned to challenge│    │  - Session closed permanently │
└───────────────────────────────┘     └───────────────────────────────┘
```

---

## 2. Core Architectural Principles & Boundaries

### 2.1 One WakeSession Per Alarm Occurrence
- **Strict Occurrence Idempotency**: For any given scheduled occurrence (e.g. Wednesday 07:00), the scheduler creates exactly **one** `WakeSession`.
- **Occurrence Window Guard**: Even if an occurrence is completed or abandoned within the active minute, subsequent scheduler runs within that same minute recognize the scheduled occurrence window `[occurrence_time, occurrence_time + 60s)` and skip creation.
- **Future Recurrences**: When the next scheduled recurrence arrives (e.g. Thursday 07:00), the occurrence timestamp shifts forward by 24+ hours, cleanly generating a new `WakeSession` for that new occurrence.

### 2.2 Relationship Between WakeSession and SnoozeEvent
- Snoozing operates on the **same** `WakeSession` created by the scheduler.
- A snooze does **not** create a new `WakeSession`.
- Multiple snoozes create multiple child `SnoozeEvent` records (`snooze_number = 1, 2, 3...`) associated with the parent session via `wake_session_id`.
- `WakeSession.total_snooze_count` is incremented atomically on each valid snooze.

### 2.3 Scheduler Responsibility Boundary
- The scheduler's sole responsibilities are:
  1. Evaluating whether an active recurring alarm is due for a user's timezone.
  2. Spawning the initial `WakeSession` for that occurrence.
- The scheduler does **not**:
  - Modify user alarm times or recurrence days.
  - Choose or alter wake-up challenge types.
  - Perform adaptive difficulty or ML tuning.

### 2.4 Snooze $\rightarrow$ Resume Lifecycle Boundary
- The service provides `resume_ringing` (`snoozed` $\rightarrow$ `ringing`), accessible via `PATCH /api/v1/wake-sessions/{session_id}/resume`.
- This is strictly a backend state/lifecycle transition. It does **not** implement or imply a background timer, APScheduler loop, Celery task, audio playback, or notification system.
- When an explicit resume transition occurs, `ring_resumed_at` on the latest child `SnoozeEvent` is recorded to timestamp the resume event.

### 2.5 Future Challenge Integration Boundary
- In Phase 2.7, the challenge generation and verification system will hook into `transition_to_in_progress` (`in_challenge`).
- Upon successful verification of the user's challenge task, `complete_wake_session` dismisses the alarm and records `dismissed_time` and `total_wake_delay_seconds`.
- All historical telemetry (ring duration, snooze counts, snooze intervals) will feed future ML models in Phase 3.
