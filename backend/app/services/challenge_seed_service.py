"""Dedicated seeding service for SmartWake AI Challenge Catalog.

Provides:
1. DEFAULT_CHALLENGE_CATALOG: Canonical 30-template initial catalog covering all 5
   supported challenge types ('dance', 'math', 'memory', 'tongue_twister', 'push_ups')
   across all 3 difficulty tiers ('easy', 'medium', 'hard'), with 2 templates per tier.
2. SeedResult: Dataclass reporting inserted, skipped, and total record counts.
3. seed_default_challenges: Idempotent seeding function that inserts missing records
   without duplicating or deleting existing database records.

ARCHITECTURAL RULES:
- Zero schema modifications.
- Zero AI / ML or computer vision / speech recognition dependencies.
- Memory challenges strictly employ visual sequence / spatial pattern recall (no number guessing).
- Deduplicates on the stable composite tuple: (challenge_type, difficulty_level, title).
"""
from dataclasses import dataclass
import json
from typing import Any, Dict, List, Tuple
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.constants import VALID_CHALLENGE_TYPES
from backend.app.models.challenge import Challenge

# Canonical catalog definitions (30 templates: 5 types x 3 difficulties x 2 templates)
DEFAULT_CHALLENGE_CATALOG: List[Dict[str, Any]] = [
    # =========================================================================
    # 1. MATH CHALLENGES (6 templates)
    # =========================================================================
    {
        "challenge_type": "math",
        "difficulty_level": "easy",
        "title": "Basic Addition Sprint",
        "description": "Solve a series of single-digit addition problems to wake up your mind.",
        "template_payload": json.dumps({
            "category": "arithmetic",
            "operation_types": ["addition"],
            "question_count": 3,
            "operand_min": 1,
            "operand_max": 9,
            "time_limit_seconds": 20,
            "verification_mode": "numeric_input",
        }),
        "min_duration_seconds": 10,
        "is_active": True,
    },
    {
        "challenge_type": "math",
        "difficulty_level": "easy",
        "title": "Single-Digit Subtraction Warmup",
        "description": "Complete gentle single-digit subtraction equations to start your morning.",
        "template_payload": json.dumps({
            "category": "arithmetic",
            "operation_types": ["subtraction"],
            "question_count": 3,
            "operand_min": 1,
            "operand_max": 15,
            "time_limit_seconds": 20,
            "verification_mode": "numeric_input",
        }),
        "min_duration_seconds": 10,
        "is_active": True,
    },
    {
        "challenge_type": "math",
        "difficulty_level": "medium",
        "title": "Multiplication & Division Mixer",
        "description": "Solve mixed multiplication and simple division problems to jumpstart your cognitive alertness.",
        "template_payload": json.dumps({
            "category": "arithmetic",
            "operation_types": ["multiplication", "division"],
            "question_count": 4,
            "operand_min": 2,
            "operand_max": 12,
            "time_limit_seconds": 35,
            "verification_mode": "numeric_input",
        }),
        "min_duration_seconds": 15,
        "is_active": True,
    },
    {
        "challenge_type": "math",
        "difficulty_level": "medium",
        "title": "Two-Step Arithmetic Challenge",
        "description": "Evaluate two-step chained equations combining addition and multiplication.",
        "template_payload": json.dumps({
            "category": "arithmetic",
            "operation_types": ["addition", "multiplication"],
            "question_count": 4,
            "operand_min": 2,
            "operand_max": 25,
            "time_limit_seconds": 35,
            "verification_mode": "numeric_input",
        }),
        "min_duration_seconds": 15,
        "is_active": True,
    },
    {
        "challenge_type": "math",
        "difficulty_level": "hard",
        "title": "Order of Operations Blitz",
        "description": "Solve multi-operator equations respecting BODMAS/PEMDAS order of operations.",
        "template_payload": json.dumps({
            "category": "arithmetic",
            "operation_types": ["addition", "subtraction", "multiplication", "parentheses"],
            "question_count": 5,
            "operand_min": 5,
            "operand_max": 50,
            "time_limit_seconds": 50,
            "verification_mode": "numeric_input",
        }),
        "min_duration_seconds": 25,
        "is_active": True,
    },
    {
        "challenge_type": "math",
        "difficulty_level": "hard",
        "title": "Mental Math Mixed Equation Solver",
        "description": "Quickly compute rapid-fire triple-step mental arithmetic equations.",
        "template_payload": json.dumps({
            "category": "arithmetic",
            "operation_types": ["addition", "subtraction", "multiplication", "division"],
            "question_count": 6,
            "operand_min": 10,
            "operand_max": 100,
            "time_limit_seconds": 60,
            "verification_mode": "numeric_input",
        }),
        "min_duration_seconds": 30,
        "is_active": True,
    },

    # =========================================================================
    # 2. MEMORY CHALLENGES (6 templates - strictly visual sequence / pattern recall)
    # =========================================================================
    {
        "challenge_type": "memory",
        "difficulty_level": "easy",
        "title": "Color Tile Flash Sequence",
        "description": "Observe a sequence of colored glowing tiles and tap them in the exact order shown.",
        "template_payload": json.dumps({
            "category": "visual_pattern",
            "recall_mode": "visual_sequence",
            "sequence_length": 3,
            "display_duration_seconds": 4,
            "time_limit_seconds": 20,
            "tile_palette": ["emerald", "amber", "azure", "coral"],
            "grid_dimension": "2x2",
            "verification_mode": "pattern_sequence_match",
        }),
        "min_duration_seconds": 10,
        "is_active": True,
    },
    {
        "challenge_type": "memory",
        "difficulty_level": "easy",
        "title": "3x3 Grid Pattern Memory",
        "description": "Memorize the positions of 3 highlighted cells in a 3x3 matrix and recall them accurately.",
        "template_payload": json.dumps({
            "category": "visual_pattern",
            "recall_mode": "spatial_pattern_recall",
            "matrix_size": 3,
            "highlight_count": 3,
            "display_duration_seconds": 4,
            "time_limit_seconds": 20,
            "tile_palette": ["slate", "indigo"],
            "verification_mode": "spatial_cell_match",
        }),
        "min_duration_seconds": 10,
        "is_active": True,
    },
    {
        "challenge_type": "memory",
        "difficulty_level": "medium",
        "title": "Dynamic Spatial Sequence Recall",
        "description": "Watch an expanding 5-step spatial path illuminate across the screen and recreate the path.",
        "template_payload": json.dumps({
            "category": "visual_pattern",
            "recall_mode": "dynamic_spatial_path",
            "sequence_length": 5,
            "display_duration_seconds": 6,
            "time_limit_seconds": 35,
            "grid_dimension": "3x3",
            "speed_ms_per_step": 700,
            "verification_mode": "path_order_match",
        }),
        "min_duration_seconds": 15,
        "is_active": True,
    },
    {
        "challenge_type": "memory",
        "difficulty_level": "medium",
        "title": "4x4 Matrix Pattern Memory",
        "description": "Memorize a 5-cell illuminated geometric cluster in a 4x4 grid before it disappears.",
        "template_payload": json.dumps({
            "category": "visual_pattern",
            "recall_mode": "spatial_pattern_recall",
            "matrix_size": 4,
            "highlight_count": 5,
            "display_duration_seconds": 5,
            "time_limit_seconds": 35,
            "tile_palette": ["teal", "violet"],
            "verification_mode": "cluster_cell_match",
        }),
        "min_duration_seconds": 15,
        "is_active": True,
    },
    {
        "challenge_type": "memory",
        "difficulty_level": "hard",
        "title": "Dual-Pattern Matrix Flash Grid",
        "description": "Observe two alternating high-speed visual patterns on a 5x5 grid and reproduce the combined sequence.",
        "template_payload": json.dumps({
            "category": "visual_pattern",
            "recall_mode": "dual_alternating_pattern",
            "matrix_size": 5,
            "sequence_length": 7,
            "display_duration_seconds": 6,
            "time_limit_seconds": 50,
            "tile_palette": ["cyan", "magenta", "yellow"],
            "verification_mode": "dual_sequence_match",
        }),
        "min_duration_seconds": 25,
        "is_active": True,
    },
    {
        "challenge_type": "memory",
        "difficulty_level": "hard",
        "title": "Complex Symbol Sequence Recall",
        "description": "Memorize a rapid sequence of 8 distinct geometric icons and reconstruct their chronological order.",
        "template_payload": json.dumps({
            "category": "visual_pattern",
            "recall_mode": "symbol_chronological_order",
            "sequence_length": 8,
            "display_duration_seconds": 7,
            "time_limit_seconds": 60,
            "symbol_set": ["triangle", "circle", "diamond", "hexagon", "star", "crescent"],
            "shuffle_on_recall": True,
            "verification_mode": "symbol_order_match",
        }),
        "min_duration_seconds": 30,
        "is_active": True,
    },

    # =========================================================================
    # 3. DANCE CHALLENGES (6 templates)
    # =========================================================================
    {
        "challenge_type": "dance",
        "difficulty_level": "easy",
        "title": "Morning Rhythm Groove",
        "description": "Stand up and follow a light 2-step side-to-side groove to awaken your body.",
        "template_payload": json.dumps({
            "category": "kinetic_movement",
            "routine_type": "side_step_bounce",
            "step_count": 4,
            "duration_seconds": 20,
            "tempo_bpm": 100,
            "verification_mode": "pose_motion_detection",
            "min_energy_threshold": 0.5,
        }),
        "min_duration_seconds": 15,
        "is_active": True,
    },
    {
        "challenge_type": "dance",
        "difficulty_level": "easy",
        "title": "Basic Side-Step & Arm Reach",
        "description": "Synchronize alternating side steps with overhead arm reaches to stretch and activate circulation.",
        "template_payload": json.dumps({
            "category": "kinetic_movement",
            "routine_type": "step_and_reach",
            "step_count": 4,
            "duration_seconds": 20,
            "tempo_bpm": 105,
            "verification_mode": "pose_motion_detection",
            "min_energy_threshold": 0.55,
        }),
        "min_duration_seconds": 15,
        "is_active": True,
    },
    {
        "challenge_type": "dance",
        "difficulty_level": "medium",
        "title": "Upbeat Cardio Step Combo",
        "description": "Perform a 6-step aerobic sequence incorporating high knees and cross-body taps.",
        "template_payload": json.dumps({
            "category": "kinetic_movement",
            "routine_type": "cardio_high_knees_combo",
            "step_count": 6,
            "duration_seconds": 30,
            "tempo_bpm": 120,
            "verification_mode": "pose_motion_detection",
            "min_energy_threshold": 0.7,
        }),
        "min_duration_seconds": 20,
        "is_active": True,
    },
    {
        "challenge_type": "dance",
        "difficulty_level": "medium",
        "title": "Syncopated Rhythm Routine",
        "description": "Follow a rhythmic four-count salsa-inspired box step to coordinate balance and focus.",
        "template_payload": json.dumps({
            "category": "kinetic_movement",
            "routine_type": "rhythm_box_step",
            "step_count": 6,
            "duration_seconds": 30,
            "tempo_bpm": 125,
            "verification_mode": "pose_motion_detection",
            "min_energy_threshold": 0.7,
        }),
        "min_duration_seconds": 20,
        "is_active": True,
    },
    {
        "challenge_type": "dance",
        "difficulty_level": "hard",
        "title": "Full-Body Kinetic Choreography Blast",
        "description": "Execute a continuous 8-step dynamic dance routine combining turns, squats, and arm wave accents.",
        "template_payload": json.dumps({
            "category": "kinetic_movement",
            "routine_type": "dynamic_hip_hop_groove",
            "step_count": 8,
            "duration_seconds": 45,
            "tempo_bpm": 135,
            "verification_mode": "pose_motion_detection",
            "min_energy_threshold": 0.85,
        }),
        "min_duration_seconds": 30,
        "is_active": True,
    },
    {
        "challenge_type": "dance",
        "difficulty_level": "hard",
        "title": "High-Energy Rhythm Flow",
        "description": "Complete an athletic cardio-dance interval with jumping jacks, pivot turns, and rapid tempo transitions.",
        "template_payload": json.dumps({
            "category": "kinetic_movement",
            "routine_type": "interval_cardio_dance",
            "step_count": 10,
            "duration_seconds": 50,
            "tempo_bpm": 140,
            "verification_mode": "pose_motion_detection",
            "min_energy_threshold": 0.9,
        }),
        "min_duration_seconds": 35,
        "is_active": True,
    },

    # =========================================================================
    # 4. TONGUE TWISTER CHALLENGES (6 templates)
    # =========================================================================
    {
        "challenge_type": "tongue_twister",
        "difficulty_level": "easy",
        "title": "Crisp Consonants Starter Verse",
        "description": "Recite a short, crisp alliterative phrase twice with clear diction.",
        "template_payload": json.dumps({
            "category": "speech_articulation",
            "passage_text": "She sells sea shells by the sea shore.",
            "phonetic_focus": "s_and_sh_alternation",
            "repetition_count": 2,
            "speaking_duration_seconds": 15,
            "verification_mode": "speech_stt_alignment",
            "max_word_error_rate": 0.25,
        }),
        "min_duration_seconds": 10,
        "is_active": True,
    },
    {
        "challenge_type": "tongue_twister",
        "difficulty_level": "easy",
        "title": "Alliteration Awakening Phrase",
        "description": "Articulate a brisk plosive sentence cleanly to shake off morning vocal fatigue.",
        "template_payload": json.dumps({
            "category": "speech_articulation",
            "passage_text": "Peter Piper picked a peck of pickled peppers.",
            "phonetic_focus": "plosive_p_repetition",
            "repetition_count": 2,
            "speaking_duration_seconds": 15,
            "verification_mode": "speech_stt_alignment",
            "max_word_error_rate": 0.25,
        }),
        "min_duration_seconds": 10,
        "is_active": True,
    },
    {
        "challenge_type": "tongue_twister",
        "difficulty_level": "medium",
        "title": "Sibilant S-Sound Articulation Passage",
        "description": "Clearly enunciate a multi-clause passage challenging tongue positioning and breath control.",
        "template_payload": json.dumps({
            "category": "speech_articulation",
            "passage_text": "Six slippery snails slid slowly southward down the steep stone slope.",
            "phonetic_focus": "sibilant_s_clusters",
            "repetition_count": 2,
            "speaking_duration_seconds": 25,
            "verification_mode": "speech_stt_alignment",
            "max_word_error_rate": 0.2,
        }),
        "min_duration_seconds": 15,
        "is_active": True,
    },
    {
        "challenge_type": "tongue_twister",
        "difficulty_level": "medium",
        "title": "Phonetic Friction Workout",
        "description": "Recite an intricate dental-fricative sentence without slurring consonants.",
        "template_payload": json.dumps({
            "category": "speech_articulation",
            "passage_text": "The thirty-three thieves thought that they thrilled the throne throughout Thursday.",
            "phonetic_focus": "dental_fricative_th",
            "repetition_count": 2,
            "speaking_duration_seconds": 25,
            "verification_mode": "speech_stt_alignment",
            "max_word_error_rate": 0.2,
        }),
        "min_duration_seconds": 15,
        "is_active": True,
    },
    {
        "challenge_type": "tongue_twister",
        "difficulty_level": "hard",
        "title": "Complex Multisyllabic Monologue",
        "description": "Deliver a dense tongue twister with alternating labial and dental consonant clusters at steady tempo.",
        "template_payload": json.dumps({
            "category": "speech_articulation",
            "passage_text": "How much ground would a groundhog grind if a groundhog could grind ground? A groundhog would grind all the ground he could grind.",
            "phonetic_focus": "compound_cluster_gr_nd",
            "repetition_count": 3,
            "speaking_duration_seconds": 40,
            "verification_mode": "speech_stt_alignment",
            "max_word_error_rate": 0.15,
        }),
        "min_duration_seconds": 25,
        "is_active": True,
    },
    {
        "challenge_type": "tongue_twister",
        "difficulty_level": "hard",
        "title": "Rapid Articulation Master Class",
        "description": "Speak a challenging, high-friction rhyme demanding maximum vocal agility and mental presence.",
        "template_payload": json.dumps({
            "category": "speech_articulation",
            "passage_text": "Betty Botter bought some butter, but she said the butter's bitter. If I put it in my batter, it will make my batter bitter, but a bit of better butter will make my bitter batter better.",
            "phonetic_focus": "rapid_plosive_vowel_shifts",
            "repetition_count": 2,
            "speaking_duration_seconds": 45,
            "verification_mode": "speech_stt_alignment",
            "max_word_error_rate": 0.15,
        }),
        "min_duration_seconds": 30,
        "is_active": True,
    },

    # =========================================================================
    # 5. PUSH-UPS CHALLENGES (6 templates)
    # =========================================================================
    {
        "challenge_type": "push_ups",
        "difficulty_level": "easy",
        "title": "Awakening Push-Up Starter Set",
        "description": "Perform 5 deliberate push-ups to stimulate blood flow and chest musculature.",
        "template_payload": json.dumps({
            "category": "physical_calisthenics",
            "target_repetitions": 5,
            "completion_window_seconds": 30,
            "verification_mode": "vision_pose_rep_counter",
            "min_rom_percentage": 70,
            "cadence_guideline": "controlled",
        }),
        "min_duration_seconds": 15,
        "is_active": True,
    },
    {
        "challenge_type": "push_ups",
        "difficulty_level": "easy",
        "title": "Incline / Form Check Reps",
        "description": "Execute 6 clean repetitions focusing on full core bracing and stable elbow angle.",
        "template_payload": json.dumps({
            "category": "physical_calisthenics",
            "target_repetitions": 6,
            "completion_window_seconds": 30,
            "verification_mode": "vision_pose_rep_counter",
            "min_rom_percentage": 70,
            "cadence_guideline": "controlled",
        }),
        "min_duration_seconds": 15,
        "is_active": True,
    },
    {
        "challenge_type": "push_ups",
        "difficulty_level": "medium",
        "title": "Standard Awakening Rep Cadence",
        "description": "Complete 10 full-range push-ups within 45 seconds to thoroughly wake up your nervous system.",
        "template_payload": json.dumps({
            "category": "physical_calisthenics",
            "target_repetitions": 10,
            "completion_window_seconds": 45,
            "verification_mode": "vision_pose_rep_counter",
            "min_rom_percentage": 75,
            "cadence_guideline": "moderate",
        }),
        "min_duration_seconds": 20,
        "is_active": True,
    },
    {
        "challenge_type": "push_ups",
        "difficulty_level": "medium",
        "title": "Paced Form Push-Up Routine",
        "description": "Perform 12 steady-tempo push-ups with full elbow lockout at the top of each rep.",
        "template_payload": json.dumps({
            "category": "physical_calisthenics",
            "target_repetitions": 12,
            "completion_window_seconds": 45,
            "verification_mode": "vision_pose_rep_counter",
            "min_rom_percentage": 75,
            "cadence_guideline": "moderate",
        }),
        "min_duration_seconds": 20,
        "is_active": True,
    },
    {
        "challenge_type": "push_ups",
        "difficulty_level": "hard",
        "title": "Morning Calisthenics Endurance Set",
        "description": "Power through 20 continuous full-depth push-ups to supercharge your morning adrenaline.",
        "template_payload": json.dumps({
            "category": "physical_calisthenics",
            "target_repetitions": 20,
            "completion_window_seconds": 60,
            "verification_mode": "vision_pose_rep_counter",
            "min_rom_percentage": 80,
            "cadence_guideline": "athletic",
        }),
        "min_duration_seconds": 30,
        "is_active": True,
    },
    {
        "challenge_type": "push_ups",
        "difficulty_level": "hard",
        "title": "Explosive Push-Up Intensity Set",
        "description": "Complete 25 high-intensity push-ups with dynamic upward drive and minimal resting.",
        "template_payload": json.dumps({
            "category": "physical_calisthenics",
            "target_repetitions": 25,
            "completion_window_seconds": 75,
            "verification_mode": "vision_pose_rep_counter",
            "min_rom_percentage": 85,
            "cadence_guideline": "explosive",
        }),
        "min_duration_seconds": 35,
        "is_active": True,
    },
]


@dataclass
class SeedResult:
    """Outcome summary of a challenge catalog seeding execution."""

    inserted: int
    skipped: int
    total_catalog: int
    total_in_db: int


def seed_default_challenges(db: Session) -> SeedResult:
    """Idempotently seed the master challenge catalog into the database.

    Checks whether an equivalent challenge template already exists by examining
    the composite key (challenge_type, difficulty_level, title). Inserts only
    missing records, commits safely, and leaves existing records completely intact.

    Args:
        db: Active SQLAlchemy database session.

    Returns:
        SeedResult with inserted, skipped, total_catalog, and total_in_db counts.
    """
    # 1. Fetch existing composite keys from database to avoid duplicate inserts
    stmt = select(Challenge.challenge_type, Challenge.difficulty_level, Challenge.title)
    existing_rows = db.execute(stmt).all()
    existing_keys = {(r[0], r[1], r[2]) for r in existing_rows}

    inserted_count = 0
    skipped_count = 0

    for item in DEFAULT_CHALLENGE_CATALOG:
        key = (item["challenge_type"], item["difficulty_level"], item["title"])
        if key in existing_keys:
            skipped_count += 1
            continue

        # Create new Challenge model instance
        challenge = Challenge(
            challenge_type=item["challenge_type"],
            difficulty_level=item["difficulty_level"],
            title=item["title"],
            description=item["description"],
            template_payload=item["template_payload"],
            min_duration_seconds=item["min_duration_seconds"],
            is_active=item["is_active"],
        )
        db.add(challenge)
        existing_keys.add(key)
        inserted_count += 1

    if inserted_count > 0:
        db.commit()

    # Query total records currently in challenges table
    total_in_db = len(existing_keys)

    return SeedResult(
        inserted=inserted_count,
        skipped=skipped_count,
        total_catalog=len(DEFAULT_CHALLENGE_CATALOG),
        total_in_db=total_in_db,
    )
