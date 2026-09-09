# SmartWake AI — Snooze Tracking Architecture & Lifecycle

This document details the backend service layer and API architecture for **Phase 2.6.3: Snooze Tracking** in **SmartWake AI**.

---

## 1. Core Principle & Purpose

```
┌────────────────────────────────────────────────────────┐
│                   BEHAVIORAL TELEMETRY                 │
│               (Historical Tracking Only)               │
├────────────────────────────────────────────────────────┤
│  - Snoozing records granular sleep-inertia behavior    │
│  - Snoozing does NOT dismiss or complete an alarm      │
│  - WakeSession remains active until challenge is passed│
│  - Snooze data is collected now; future Phase 3 will   │
│    use this telemetry for adaptive difficulty ML       │
└────────────────────────────────────────────────────────┘
```

---

## 2. Snooze Tracking Lifecycle Flow

```
                     Scheduled Alarm Rings
                               ↓
                   WakeSession status = "ringing"
                               ↓
                      User Requests Snooze
                               ↓
                     Validate Session State
             (must be active: 'ringing' or 'snoozed')
                               ↓
                    Create SnoozeEvent Record
              - wake_session_id = session.id
              - snooze_number = total_snooze_count + 1
              - snoozed_at = current timestamp
              - ring_resumed_at = None (re-ring scheduler deferred)
              - snooze_duration_minutes = duration (model default 5)
                               ↓
                   Update WakeSession State
              - total_snooze_count += 1
              - status = "snoozed"
                               ↓
                 WakeSession Remains Active
                               ↓
            (Future re-ring & challenge completion)
```

---

## 3. Key Design Decisions & Guardrails

1. **Single Occurrence Lifecycle**:
   Snoozing does **not** create a new `WakeSession`. The existing `WakeSession` remains the single canonical lifecycle record for that alarm occurrence. Multiple snoozes create multiple child `SnoozeEvent` records, incrementing `total_snooze_count` on the parent session.

2. **Allowed States vs. Terminal Rejection**:
   - Permitted: `ringing` $\rightarrow$ `snoozed`, or `snoozed` $\rightarrow$ `snoozed` (repeated snoozing).
   - Rejected: Terminal sessions (`completed`, `abandoned`) strictly reject snooze attempts with `InvalidSessionTransitionError` (HTTP 400).

3. **Duration & Limits**:
   - Uses the existing `snooze_duration_minutes` field on `SnoozeEvent` (model default: 5 minutes).
   - Negative or zero durations are rejected with `InvalidSnoozeDurationError` (HTTP 400).
   - No arbitrary product-level maximum snooze limits are enforced in this phase; actual snooze behavior is recorded faithfully.

4. **Re-Ring Resumption Timestamp**:
   `ring_resumed_at` on `SnoozeEvent` is left as `None`. Actual scheduler re-ring and timer loops will be handled in subsequent runtime phases.

5. **Atomicity & Transaction Safety**:
   `SnoozeEvent` creation and `WakeSession` state updates occur in a single atomic SQLAlchemy transaction. Any failure triggers a clean rollback, preventing orphaned telemetry records.
