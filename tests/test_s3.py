from __future__ import annotations

import sys

from operatingsystembackup.destinations.s3 import ensure_boto3
from operatingsystembackup.errors import OptionalDependencyError


def test_missing_boto3(monkeypatch):
    monkeypatch.setitem(sys.modules, "boto3", None)
    try:
        ensure_boto3()
        raise AssertionError("expected OptionalDependencyError")
    except OptionalDependencyError as exc:
        assert "operatingsystembackup[s3]" in str(exc)
