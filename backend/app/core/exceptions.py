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


