"""Application-wide constants and canonical sets for SmartWake AI."""
from typing import Set

# Canonical wake-up task types supported by SmartWake AI.
# The user explicitly selects the challenge type when creating an alarm.
# The scheduler and ML engines NEVER alter or choose the challenge type.
# NOTE: 'memory' represents an actual visual sequence/pattern recall challenge, strictly NOT number guessing.
VALID_CHALLENGE_TYPES: Set[str] = {
    "dance",
    "math",
    "memory",
    "tongue_twister",
    "push_ups",
}

# Forbidden challenge types explicitly rejected to prevent sleepy bypass or inappropriate tasks
FORBIDDEN_CHALLENGE_TYPES: Set[str] = {
    "number_guessing",
    "guess_number",
    "numeric_memory",
}
