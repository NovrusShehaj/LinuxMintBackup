from __future__ import annotations

from operatingsystembackup.errors import (
    ArchiveError,
    BackupPermissionError,
    CloudAuthError,
    ConfigError,
    DestinationLoopError,
    DisconnectedDestinationError,
    InaccessibleSourceError,
    IncompatibleManifestError,
    InsufficientSpaceError,
    NetworkError,
    OptionalDependencyError,
    OSBackupError,
    PackageManagerUnavailableError,
    PartialBackupError,
    UnsupportedDistributionError,
    UnsupportedPlatformError,
    UnwritableDestinationError,
)
from operatingsystembackup.logging_setup import redact


def test_exit_codes():
    mapping = {
        ConfigError: 2,
        UnsupportedPlatformError: 3,
        UnsupportedDistributionError: 4,
        InaccessibleSourceError: 5,
        UnwritableDestinationError: 6,
        DestinationLoopError: 6,
        DisconnectedDestinationError: 7,
        InsufficientSpaceError: 8,
        OptionalDependencyError: 9,
        PackageManagerUnavailableError: 10,
        CloudAuthError: 11,
        NetworkError: 12,
        ArchiveError: 13,
        BackupPermissionError: 14,
        PartialBackupError: 15,
        IncompatibleManifestError: 16,
    }
    for cls, code in mapping.items():
        exc = cls("msg")
        assert exc.exit_code == code
        assert str(exc) == "msg"
        assert isinstance(exc, OSBackupError)


def test_redact_secrets():
    text = redact("key AKIAIOSFODNN7EXAMPLE and Bearer abc.def and AWS_SECRET_ACCESS_KEY=wJalr")
    assert "AKIAIOSFODNN7EXAMPLE" not in text
    assert "AKIA***" in text
    assert "Bearer ***" in text or "Bearer" in text
    assert "wJalr" not in text
