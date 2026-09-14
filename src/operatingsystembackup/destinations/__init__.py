"""Destination registry: external, internal, zip-home, cloud-s3."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from operatingsystembackup.errors import ConfigError, UnsupportedPlatformError

DESTINATION_TYPES = ("external", "internal", "zip-home", "cloud")
DESTINATION_REGISTRY = {
    "external": "local",
    "internal": "local",
    "zip-home": "zip-home",
    "cloud": "cloud-s3",
    "cloud-s3": "cloud-s3",
}


def list_destination_types() -> list[str]:
    return list(DESTINATION_TYPES)


def get_destination(
    kind: str,
    *,
    path: Path | None,
    sources: list[Path],
    config: dict[str, Any] | None = None,
    zip_dir: Path | None = None,
    cloud_provider: Any | None = None,
):
    """Build a destination provider. cloud_provider is injectable for tests."""
    from operatingsystembackup.destinations.cloud import CloudDestination
    from operatingsystembackup.destinations.local import LocalDriveDestination
    from operatingsystembackup.destinations.s3 import S3Provider, ensure_boto3
    from operatingsystembackup.destinations.zip_home import ZipHomeDestination

    key = (kind or "").strip().lower()
    if key not in DESTINATION_REGISTRY:
        raise UnsupportedPlatformError(
            f"unknown destination type {kind!r}. Supported: {', '.join(DESTINATION_TYPES)}"
        )
    impl = DESTINATION_REGISTRY[key]
    cfg = config or {}
    if impl == "local":
        if path is None:
            raise ConfigError("local destinations require --destination PATH")
        local_kind = "external" if key == "external" else "internal"
        return LocalDriveDestination(path, kind=local_kind, sources=sources)
    if impl == "zip-home":
        archive = cfg.get("archive") or {}
        chosen = zip_dir
        if chosen is None and archive.get("zip_dir"):
            chosen = Path(archive["zip_dir"]).expanduser()
        compression = archive.get("compression") or "deflate"
        return ZipHomeDestination(directory=chosen, sources=sources, compression=compression)
    cloud_cfg = cfg.get("cloud") or {}
    provider = cloud_provider
    if provider is None:
        ensure_boto3()
        bucket = cloud_cfg.get("bucket")
        if not bucket:
            raise ConfigError("cloud destination requires cloud.bucket in config")
        provider = S3Provider(
            bucket=str(bucket),
            profile=cloud_cfg.get("profile"),
            endpoint_url=cloud_cfg.get("endpoint_url"),
            region=cloud_cfg.get("region"),
        )
    prefix = str(cloud_cfg.get("prefix") or "osbackup")
    return CloudDestination(provider, prefix=prefix, sources=sources)
