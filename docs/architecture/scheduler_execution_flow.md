# SmartWake AI — Scheduler Execution Architecture & Flow

This document details the backend service layer architecture for **Phase 2.6.2.2: Scheduler Execution** in **SmartWake AI**.

---

## 1. Core Principle & Constraints

```
┌────────────────────────────────────────────────────────┐
│                   USER CONFIGURATION                   │
│                     (User Controls)                    │
├────────────────────────────────────────────────────────┤
│  1. Scheduled Alarm Time (e.g., '07:00 AM')            │
│  2. Recurrence Days of Week (e.g., [0, 1, 2, 3, 4])    │
│  3. Wake-up Challenge Type (e.g., 'tongue_twister')    │
│  4. Baseline Difficulty (e.g., 'adaptive')             │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│                   SCHEDULER SERVICE                    │
│            (Deterministic Execution Engine)            │
├────────────────────────────────────────────────────────┤
│  - Evaluates whether recurring alarms are due          │
│  - Guarantees duplicate-prevention within same minute  │
│  - Creates initial 'ringing' WakeSessions              │
│                                                        │
│  SCHEDULER DOES NOT:                                   │
│  ❌ Modify user alarm time or recurrence days          │
│  ❌ Change or choose challenge type                    │
│  ❌ Alter baseline difficulty preference               │
│  ❌ Perform adaptive ML decisions                      │
└────────────────────────────────────────────────────────┘
```

---

## 2. Scheduler Execution Flow

```
                current_time (Timezone-Aware UTC)
                                ↓
                get_due_alarms(db, current_time)
                                ↓
                    For each active due alarm:
                                ↓
            has_active_or_occurrence_session(db, alarm_id, occ_time)
                                ↓
                 ┌──────────────┴──────────────┐
                 │                             │
              [ True ]                      [ False ]
                 │                             │
                 ▼                             ▼
               SKIP                 create_wake_session(...)
      (increment skipped count)                │
                                               ▼
                                   WakeSession created
                                  (status = 'ringing')
                                               │
                                               ▼
                                      Commit Transaction
```

---

## 3. Duplicate Prevention & Occurrence Safety

### 3.1 The Problem
In production, a background scheduler or cron process may poll every 5, 10, or 15 seconds:
- `07:00:05` $\rightarrow$ Alarm is due $\rightarrow$ `WakeSession` created.
- `07:00:20` $\rightarrow$ Scheduler checks again during the same minute.
- `07:00:40` $\rightarrow$ Scheduler checks again during the same minute.

Without guards, multiple active `WakeSession` records could be created for the same alarm occurrence.

Furthermore, if the user immediately completes or dismisses the alarm at `07:00:15` (transitioning status to terminal `'completed'`), a naive active-only check at `07:00:20` would find no active session and erroneously create a duplicate session for the already-dismissed alarm.

### 3.2 The Solution
SmartWake AI solves this with a two-tier guard in `has_active_or_occurrence_session`:
1. **Active Session Guard**:
   Checks if any session for `alarm_id` has `status in ('ringing', 'in_challenge', 'snoozed')`. If an ongoing session exists, the scheduler skips creation.
2. **Occurrence Window Guard**:
   Calculates the exact scheduled occurrence UTC timestamp for this minute (`HH:MM:00`). If any session (even terminal `'completed'` or `'abandoned'`) was already scheduled within this 1-minute window `[occurrence_time, occurrence_time + 60s)`, the scheduler skips creation.

### 3.3 Assumptions & Limitations
- **No Schema Redesign**: Does not introduce an `occurrence_id` column or modify database tables.
- **Relies on Existing State**: Relies entirely on `WakeSession.status` and `WakeSession.scheduled_time` to maintain occurrence idempotency.
- **Next Day Safe**: On the subsequent recurrence day (e.g. tomorrow at `07:00:05`), the occurrence window shifts forward by 24 hours, safely permitting the creation of a new session for the new day's occurrence.
