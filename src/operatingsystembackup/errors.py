"""Typed errors for OperatingSystemBackup. CLI maps these to exit codes 2–20."""

from __future__ import annotations


class OSBackupError(Exception):
    """Base error for expected backup failures (no traceback at default verbosity)."""

    exit_code = 2

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ConfigError(OSBackupError):
    """Invalid, missing, or unsafe configuration."""

    exit_code = 2


class UnsupportedPlatformError(OSBackupError):
    exit_code = 3


class UnsupportedDistributionError(OSBackupError):
    exit_code = 4


class InaccessibleSourceError(OSBackupError):
    exit_code = 5


class UnwritableDestinationError(OSBackupError):
    exit_code = 6


class DestinationLoopError(UnwritableDestinationError):
    """Destination path is inside a backup source (would copy the backup into itself)."""

    exit_code = 6


class DisconnectedDestinationError(OSBackupError):
    exit_code = 7


class InsufficientSpaceError(OSBackupError):
    exit_code = 8


class OptionalDependencyError(OSBackupError):
    exit_code = 9


class PackageManagerUnavailableError(OSBackupError):
    exit_code = 10


class CloudAuthError(OSBackupError):
    exit_code = 11


class NetworkError(OSBackupError):
    exit_code = 12


class ArchiveError(OSBackupError):
    exit_code = 13


class BackupPermissionError(OSBackupError):
    """Wraps builtin PermissionError for CLI mapping without shadowing the builtin."""

    exit_code = 14


class PartialBackupError(OSBackupError):
    exit_code = 15


class IncompatibleManifestError(OSBackupError):
    exit_code = 16
