"""Deterministic synthetic dataset generator for ML model development.

CRITICAL PRODUCT & ML SAFETY RULES:
1. Pure development artifact: NEVER connects to or inserts records into smartwake.db.
2. Fully deterministic generation: Uses a fixed random seed (default=42).
3. Covers all 5 canonical challenge types: dance, math, memory, tongue_twister, push_ups.
4. Generates realistic but artificial user behavior profiles (early riser, heavy snoozer, etc.).
5. Exports clean synthetic data to ml/data/raw/ for offline development and validation.
"""
import csv
import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

# Ensure project root is in sys.path when executed directly
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from ml.preprocessing.feature_schema import (
    ALL_DATASET_COLUMNS,
    FEATURE_COLUMNS,
    METADATA_COLUMNS,
    TARGET_COLUMNS,
    ChallengeFeatureRecord,
)

CANONICAL_CHALLENGE_TYPES = [
    "dance",
    "math",
    "memory",
    "tongue_twister",
    "push_ups",
]

DIFFICULTY_LEVELS = ["easy", "medium", "hard"]
DIFFICULTY_PREFERENCES = ["adaptive", "easy", "medium", "hard"]


class SyntheticMLDataGenerator:
    """Generates deterministic synthetic user waking behavior and challenge attempt datasets."""

    def __init__(self, seed: int = 42):
        self.seed = seed
        self.rng = random.Random(seed)

    def generate(
        self,
        num_users: int = 10,
        days_per_user: int = 30,
        output_dir: Optional[str] = None,
    ) -> List[ChallengeFeatureRecord]:
        """Generate a deterministic synthetic dataset across multiple users and days.

        Args:
            num_users: Number of synthetic user profiles to simulate.
            days_per_user: Days of history to generate per user.
            output_dir: Directory to write json and csv files to. If None, uses ml/data/raw/.

        Returns:
            List of ChallengeFeatureRecord instances.
        """
        self.rng.seed(self.seed)

        if output_dir is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))  # ml directory
            output_dir = os.path.join(base_dir, "data", "raw")
        os.makedirs(output_dir, exist_ok=True)

        start_date = datetime(2026, 1, 1, 7, 0, 0, tzinfo=timezone.utc)
        all_records: List[ChallengeFeatureRecord] = []

        # Define 5 synthetic persona archetypes
        personas = [
            {"name": "high_performer", "snooze_prob": 0.15, "fail_prob": 0.05, "avg_dur": 12.0},
            {"name": "heavy_snoozer", "snooze_prob": 0.70, "fail_prob": 0.25, "avg_dur": 35.0},
            {"name": "struggling_riser", "snooze_prob": 0.50, "fail_prob": 0.35, "avg_dur": 45.0},
            {"name": "average_consistent", "snooze_prob": 0.30, "fail_prob": 0.15, "avg_dur": 22.0},
            {"name": "weekend_sleeper", "snooze_prob": 0.25, "fail_prob": 0.12, "avg_dur": 18.0},
        ]

        attempt_id_counter = 1
        session_id_counter = 1

        for user_idx in range(num_users):
            user_id = 1001 + user_idx
            persona = personas[user_idx % len(personas)]

            # User-level state trackers
            user_sessions_history: List[Dict[str, Any]] = []
            user_attempts_history: List[Dict[str, Any]] = []

            # Primary challenge preference for this user
            favorite_challenge = CANONICAL_CHALLENGE_TYPES[user_idx % len(CANONICAL_CHALLENGE_TYPES)]

            for day_idx in range(days_per_user):
                scheduled_date = start_date + timedelta(days=day_idx, hours=user_idx % 3)
                is_weekend = 1 if scheduled_date.weekday() >= 5 else 0

                # 80% of the time user uses favorite, 20% random other type
                if self.rng.random() < 0.8:
                    chosen_type = favorite_challenge
                else:
                    chosen_type = self.rng.choice(CANONICAL_CHALLENGE_TYPES)

                diff_pref = self.rng.choice(DIFFICULTY_PREFERENCES)

                # Determine snooze count for this session
                snooze_prob = persona["snooze_prob"]
                if is_weekend:
                    snooze_prob = min(0.9, snooze_prob + 0.2)

                snooze_count = 0
                while self.rng.random() < snooze_prob and snooze_count < 4:
                    snooze_count += 1

                wake_delay_seconds = snooze_count * 300.0 + self.rng.uniform(10.0, 90.0)

                # Prior session aggregates
                prior_sessions_count = len(user_sessions_history)
                successful_sessions_count = sum(1 for s in user_sessions_history if s["status"] == "completed")
                failed_sessions_count = sum(1 for s in user_sessions_history if s["status"] == "abandoned")
                hist_success_rate = (
                    round(successful_sessions_count / prior_sessions_count, 4) if prior_sessions_count > 0 else 0.0
                )

                all_prior_snoozes = [s["snooze_count"] for s in user_sessions_history]
                total_snooze_count = sum(all_prior_snoozes)
                avg_snooze_count = (
                    round(total_snooze_count / prior_sessions_count, 4) if prior_sessions_count > 0 else 0.0
                )
                recent_snooze_count = user_sessions_history[-1]["snooze_count"] if user_sessions_history else 0

                # Prior attempts aggregates
                total_attempts_count = len(user_attempts_history)
                avg_attempts_per_session = (
                    round(total_attempts_count / prior_sessions_count, 4) if prior_sessions_count > 0 else 0.0
                )

                successful_durations = [
                    a["duration"] for a in user_attempts_history if a["is_successful"] and a["duration"] > 0
                ]
                avg_completion_time = (
                    round(sum(successful_durations) / len(successful_durations), 4)
                    if successful_durations
                    else 0.0
                )

                # Recent attempts (rolling 5)
                recent_attempts = user_attempts_history[-5:]
                recent_success_rate = (
                    round(sum(1 for a in recent_attempts if a["is_successful"]) / len(recent_attempts), 4)
                    if recent_attempts
                    else 0.0
                )

                # Challenge-type specific historical aggregates
                type_attempts = [a for a in user_attempts_history if a["type"] == chosen_type]
                type_total = len(type_attempts)
                type_success = sum(1 for a in type_attempts if a["is_successful"])
                type_success_rate = round(type_success / type_total, 4) if type_total > 0 else 0.0
                type_durs = [a["duration"] for a in type_attempts if a["is_successful"] and a["duration"] > 0]
                type_avg_dur = round(sum(type_durs) / len(type_durs), 4) if type_durs else 0.0

                type_sessions = set(a["session_id"] for a in type_attempts)
                type_avg_att_per_sess = (
                    round(type_total / len(type_sessions), 4) if type_sessions else 0.0
                )

                # Difficulty level metrics for this type
                easy_atts = [a for a in type_attempts if a["diff"] == "easy"]
                med_atts = [a for a in type_attempts if a["diff"] == "medium"]
                hard_atts = [a for a in type_attempts if a["diff"] == "hard"]

                easy_rate = round(sum(1 for a in easy_atts if a["is_successful"]) / len(easy_atts), 4) if easy_atts else 0.0
                med_rate = round(sum(1 for a in med_atts if a["is_successful"]) / len(med_atts), 4) if med_atts else 0.0
                hard_rate = round(sum(1 for a in hard_atts if a["is_successful"]) / len(hard_atts), 4) if hard_atts else 0.0

                # Similar hour snooze average
                similar_hour_snoozes = [
                    s["snooze_count"]
                    for s in user_sessions_history
                    if abs(s["hour"] - scheduled_date.hour) <= 1
                ]
                hist_snooze_similar = (
                    round(sum(similar_hour_snoozes) / len(similar_hour_snoozes), 4)
                    if similar_hour_snoozes
                    else 0.0
                )

                # Now simulate attempt outcome
                fail_chance = persona["fail_prob"]
                if snooze_count >= 2:
                    fail_chance += 0.15
                if diff_pref == "hard":
                    fail_chance += 0.15
                elif diff_pref == "easy":
                    fail_chance = max(0.02, fail_chance - 0.1)

                is_successful = 1 if self.rng.random() > fail_chance else 0
                duration = round(max(3.0, self.rng.gauss(persona["avg_dur"], 5.0)), 2)
                verification_score = (
                    round(self.rng.uniform(0.75, 1.0), 3) if is_successful else round(self.rng.uniform(0.1, 0.65), 3)
                )

                current_session_id = session_id_counter
                current_attempt_id = attempt_id_counter

                record = ChallengeFeatureRecord(
                    user_id=user_id,
                    wake_session_id=current_session_id,
                    challenge_attempt_id=current_attempt_id,
                    alarm_id=2000 + user_idx,
                    timestamp=scheduled_date.isoformat(),
                    # User history
                    user_total_wake_sessions=prior_sessions_count,
                    user_successful_wake_sessions=successful_sessions_count,
                    user_failed_wake_sessions=failed_sessions_count,
                    user_historical_success_rate=hist_success_rate,
                    user_avg_completion_time_seconds=avg_completion_time,
                    user_avg_attempts_per_session=avg_attempts_per_session,
                    user_avg_snooze_count=avg_snooze_count,
                    user_total_snooze_count=total_snooze_count,
                    user_recent_snooze_count=recent_snooze_count,
                    user_recent_challenge_success_rate=recent_success_rate,
                    # Challenge history
                    challenge_type_total_attempts=type_total,
                    challenge_type_successful_attempts=type_success,
                    challenge_type_success_rate=type_success_rate,
                    challenge_type_avg_completion_time=type_avg_dur,
                    challenge_type_avg_attempts_per_session=type_avg_att_per_sess,
                    challenge_type_easy_attempts=len(easy_atts),
                    challenge_type_easy_success_rate=easy_rate,
                    challenge_type_medium_attempts=len(med_atts),
                    challenge_type_medium_success_rate=med_rate,
                    challenge_type_hard_attempts=len(hard_atts),
                    challenge_type_hard_success_rate=hard_rate,
                    # Snooze history
                    current_session_snooze_count=snooze_count,
                    current_session_snooze_duration_minutes=snooze_count * 5,
                    current_session_wake_delay_seconds=wake_delay_seconds,
                    # Alarm context
                    alarm_scheduled_hour=scheduled_date.hour,
                    alarm_scheduled_minute=scheduled_date.minute,
                    alarm_day_of_week=scheduled_date.weekday(),
                    alarm_is_weekend=is_weekend,
                    historical_snooze_avg_around_alarm_time=hist_snooze_similar,
                    # Current context
                    selected_challenge_type=chosen_type,
                    user_selected_difficulty=diff_pref,
                    is_adaptive_preference=1 if diff_pref == "adaptive" else 0,
                    # Target labels
                    target_is_successful=is_successful,
                    target_duration_seconds=duration,
                    target_verification_score=verification_score,
                    target_attempt_number=1,
                )

                all_records.append(record)

                # Commit to synthetic state history for next iterations
                user_attempts_history.append({
                    "session_id": current_session_id,
                    "attempt_id": current_attempt_id,
                    "type": chosen_type,
                    "diff": diff_pref if diff_pref in DIFFICULTY_LEVELS else "medium",
                    "is_successful": bool(is_successful),
                    "duration": duration,
                })

                user_sessions_history.append({
                    "session_id": current_session_id,
                    "hour": scheduled_date.hour,
                    "snooze_count": snooze_count,
                    "status": "completed" if is_successful else "abandoned",
                })

                attempt_id_counter += 1
                session_id_counter += 1

        # Write out to JSON
        json_path = os.path.join(output_dir, "synthetic_challenge_attempts.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump([r.to_dict(include_targets=True, include_metadata=True) for r in all_records], f, indent=2)

        # Write out to CSV
        csv_path = os.path.join(output_dir, "synthetic_challenge_features.csv")
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=ALL_DATASET_COLUMNS)
            writer.writeheader()
            for r in all_records:
                writer.writerow(r.to_dict(include_targets=True, include_metadata=True))

        return all_records


def generate_synthetic_dataset(seed: int = 42) -> List[ChallengeFeatureRecord]:
    """Convenience helper to generate deterministic synthetic dataset."""
    generator = SyntheticMLDataGenerator(seed=seed)
    return generator.generate()


if __name__ == "__main__":
    generate_synthetic_dataset()
