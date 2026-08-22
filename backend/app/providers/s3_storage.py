"""Encrypted, tenant-isolated S3 raw provider object storage."""

from __future__ import annotations

import hashlib
import json

from app.providers.models import RawProviderObject
from app.providers.raw_storage import RawProviderDataStore


class S3RawProviderDataStore(RawProviderDataStore):
    def __init__(self, *, bucket: str, kms_key_id: str, client=None) -> None:
        if client is None:
            import boto3
            client = boto3.client("s3")
        self.client, self.bucket, self.kms_key_id = client, bucket, kms_key_id

    @staticmethod
    def merchant_partition(merchant_id: str) -> str:
        return hashlib.sha256(merchant_id.encode()).hexdigest()[:32]

    def _key(self, item: RawProviderObject) -> str:
        received = item.received_at
        safe_type = item.provider_object_type.replace("/", "_")
        safe_id = hashlib.sha256(item.provider_object_id.encode()).hexdigest()[:32]
        return (f"merchant/{self.merchant_partition(item.merchant_id)}/{item.provider.lower()}/"
                f"{received:%Y/%m/%d}/{safe_type}/{safe_id}.json")

    def put(self, item: RawProviderObject) -> str:
        key = self._key(item)
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=item.model_dump_json().encode(),
            ContentType="application/json",
            ServerSideEncryption="aws:kms",
            SSEKMSKeyId=self.kms_key_id,
            Metadata={"raw-id": item.id, "merchant-partition": self.merchant_partition(item.merchant_id),
                      "schema-version": item.schema_version, "source": item.source},
        )
        return f"s3://{self.bucket}/{key}"

    def get(self, raw_id: str, merchant_id: str) -> RawProviderObject | None:
        prefix = f"s3://{self.bucket}/"
        if not raw_id.startswith(prefix):
            return None
        key = raw_id.removeprefix(prefix)
        expected = f"merchant/{self.merchant_partition(merchant_id)}/"
        if not key.startswith(expected):
            return None
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
        except self.client.exceptions.NoSuchKey:
            return None
        item = RawProviderObject.model_validate(json.loads(response["Body"].read()))
        return item if item.merchant_id == merchant_id else None
