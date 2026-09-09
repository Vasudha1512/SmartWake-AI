"""Custom domain exceptions for SmartWake AI."""


class SmartWakeException(Exception):
    """Base exception for all SmartWake AI domain errors."""
    pass


class UserNotFoundError(SmartWakeException):
    """Raised when a requested user does not exist."""
    pass


class UserAlreadyExistsError(SmartWakeException):
    """Raised when attempting to create a user with a duplicate username or email."""
    pass


class InvalidChallengeTypeError(SmartWakeException):
    """Raised when an unsupported challenge/task type is specified."""
    pass


class ChallengeNotFoundError(SmartWakeException):
    """Raised when a requested challenge is not found in the catalog."""
    pass


class InvalidDifficultyError(SmartWakeException):
    """Raised when an invalid difficulty preference is specified."""
    pass


class InvalidAlarmTimeError(SmartWakeException):
    """Raised when alarm time does not match 24-hour 'HH:MM' format."""
    pass


class InvalidTimezoneError(SmartWakeException):
    """Raised when an invalid or unresolvable IANA timezone is specified."""
    pass


class InvalidDaysOfWeekError(SmartWakeException):
    """Raised when an invalid days_of_week configuration is specified."""
    pass


class AlarmNotFoundError(SmartWakeException):
    """Raised when a requested alarm does not exist."""
    pass


class WakeSessionNotFoundError(SmartWakeException):
    """Raised when a requested wake session does not exist."""
    pass


class AlarmOwnershipError(SmartWakeException):
    """Raised when an alarm does not belong to the specified user."""
    pass


class InactiveAlarmError(SmartWakeException):
    """Raised when attempting to start a wake session for a deactivated alarm."""
    pass


class InvalidSessionTransitionError(SmartWakeException):
    """Raised when an illegal or nonsensical wake session status transition is attempted."""
    pass


class ActiveSessionExistsError(SmartWakeException):
    """Raised when an active wake session is already running for the specified alarm."""
    pass


class InvalidSnoozeDurationError(SmartWakeException, ValueError):
    """Raised when an invalid snooze duration (e.g. negative or zero) is specified."""
    pass


class InactiveChallengeError(SmartWakeException):
    """Raised when attempting to generate a challenge from a deactivated template."""
    pass


class InvalidTemplatePayloadError(SmartWakeException):
    """Raised when a challenge template payload cannot be parsed as JSON or violates JSON schema."""
    pass


class TemplateConfigurationError(SmartWakeException):
    """Raised when required configuration keys for a specific challenge type are missing."""
    pass


class ChallengeAttemptNotFoundError(SmartWakeException):
    """Raised when a requested challenge attempt does not exist."""
    pass


class ChallengeAttemptOwnershipError(SmartWakeException):
    """Raised when a user attempts to access or submit an attempt belonging to another user."""
    pass


class ActiveChallengeAttemptExistsError(SmartWakeException):
    """Raised when an uncompleted attempt is already in progress for a wake session."""
    pass


class ChallengeAttemptCompletedError(SmartWakeException):
    """Raised when attempting to submit an already completed challenge attempt."""
    pass
