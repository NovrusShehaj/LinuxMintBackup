"""Optional S3-compatible cloud provider (boto3 extra)."""

from __future__ import annotations

import logging
from pathlib import Path

from operatingsystembackup.errors import CloudAuthError, NetworkError, OptionalDependencyError

log = logging.getLogger("operatingsystembackup")


def ensure_boto3():
    try:
        import boto3  # type: ignore[import-untyped]
    except ImportError as exc:
        raise OptionalDependencyError(
            "cloud backups require boto3. Install with: pip install 'operatingsystembackup[s3]'"
        ) from exc
    return boto3


class S3Provider:
    def __init__(
        self,
        bucket: str,
        *,
        profile: str | None = None,
        endpoint_url: str | None = None,
        region: str | None = None,
    ) -> None:
        self.bucket = bucket
        self.profile = profile
        self.endpoint_url = endpoint_url
        self.region = region
        self._client = None

    def client(self):
        if self._client is None:
            boto3 = ensure_boto3()
            session_kwargs = {}
            if self.profile:
                session_kwargs["profile_name"] = self.profile
            session = boto3.session.Session(**session_kwargs)
            client_kwargs = {}
            if self.endpoint_url:
                client_kwargs["endpoint_url"] = self.endpoint_url
            if self.region:
                client_kwargs["region_name"] = self.region
            self._client = session.client("s3", **client_kwargs)
        return self._client

    def probe_auth(self) -> None:
        try:
            self.client().head_bucket(Bucket=self.bucket)
        except Exception as exc:
            _raise_cloud(exc)

    def upload(self, local_path: Path, key: str) -> None:
        try:
            self.client().upload_file(str(local_path), self.bucket, key)
        except Exception as exc:
            _raise_cloud(exc)

    def download(self, key: str, local_path: Path) -> None:
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        try:
            self.client().download_file(self.bucket, key, str(local_path))
        except Exception as exc:
            _raise_cloud(exc)

    def list_prefix(self, prefix: str) -> list[str]:
        keys: list[str] = []
        token = None
        try:
            while True:
                kwargs = {"Bucket": self.bucket, "Prefix": prefix}
                if token:
                    kwargs["ContinuationToken"] = token
                response = self.client().list_objects_v2(**kwargs)
                for item in response.get("Contents") or []:
                    keys.append(item["Key"])
                if not response.get("IsTruncated"):
                    break
                token = response.get("NextContinuationToken")
        except Exception as exc:
            _raise_cloud(exc)
        return keys

    def delete_key(self, key: str) -> None:
        try:
            self.client().delete_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            _raise_cloud(exc)


def _raise_cloud(exc: Exception) -> None:
    name = type(exc).__name__
    text = str(exc)
    lowered = text.lower()
    code = ""
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        code = str((response.get("Error") or {}).get("Code") or "")
    if code in {"403", "AccessDenied", "InvalidAccessKeyId", "SignatureDoesNotMatch"} or "access denied" in lowered:
        raise CloudAuthError(f"S3 authentication failed: {text}") from exc
    if code in {"NoSuchBucket", "404", "NoSuchKey", "404"} or name in {"NoSuchBucket", "NoSuchKey"}:
        raise NetworkError(f"S3 object error: {text}") from exc
    raise NetworkError(f"S3 request failed: {text}") from exc
