"""S3-compatible object storage abstraction with a local filesystem backend for development."""

import uuid
from pathlib import Path

from app.core.config import settings


class LocalStorage:
    def __init__(self, root: str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if not str(p).startswith(str(self.root.resolve())):
            raise ValueError("invalid storage key")
        return p

    def put(self, key: str, data: bytes) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


class S3Storage:
    def __init__(self) -> None:
        import boto3

        self.bucket = settings.s3_bucket
        self.client = boto3.client("s3", region_name=settings.s3_region, endpoint_url=settings.s3_endpoint_url or None)

    def put(self, key: str, data: bytes) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ServerSideEncryption="AES256")

    def get(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


def get_storage():
    return S3Storage() if settings.storage_backend == "s3" else LocalStorage(settings.storage_local_path)


def object_key(org_id: uuid.UUID, filename: str) -> str:
    return f"orgs/{org_id}/{uuid.uuid4().hex}/{filename}"
