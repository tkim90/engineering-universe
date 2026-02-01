from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from eng_universe.config import Settings
from eng_universe.monitoring.logging_utils import get_event_logger

log_event = get_event_logger("r2")


@dataclass(frozen=True)
class R2Config:
    account_id: str
    access_key_id: str
    secret_access_key: str
    bucket_name: str
    region: str
    endpoint_url: str


_UNSET = object()
_CONFIG: R2Config | None | object = _UNSET
_CLIENT: object | None = None
_MISSING_LOGGED = False


def _load_config() -> R2Config | None:
    global _CONFIG, _MISSING_LOGGED
    if _CONFIG is not _UNSET:
        return _CONFIG
    if not Settings.r2_upload:
        _CONFIG = None
        return None
    missing: list[str] = []
    if not Settings.r2_account_id:
        missing.append("R2_ACCOUNT_ID")
    if not Settings.r2_access_key_id:
        missing.append("R2_ACCESS_KEY_ID")
    if not Settings.r2_secret_access_key:
        missing.append("R2_SECRET_ACCESS_KEY")
    if not Settings.r2_bucket_name:
        missing.append("R2_BUCKET_NAME")
    if missing:
        if not _MISSING_LOGGED:
            log_event("r2_skip", reason="missing_env", missing=",".join(missing))
            _MISSING_LOGGED = True
        _CONFIG = None
        return None
    endpoint_url = (
        Settings.r2_endpoint_url
        or f"https://{Settings.r2_account_id}.r2.cloudflarestorage.com"
    )
    _CONFIG = R2Config(
        account_id=Settings.r2_account_id,
        access_key_id=Settings.r2_access_key_id,
        secret_access_key=Settings.r2_secret_access_key,
        bucket_name=Settings.r2_bucket_name,
        region=Settings.r2_region,
        endpoint_url=endpoint_url,
    )
    return _CONFIG


def _get_client() -> tuple[R2Config, object] | None:
    global _CLIENT
    config = _load_config()
    if config is None:
        return None
    if _CLIENT is None:
        _CLIENT = boto3.client(
            "s3",
            endpoint_url=config.endpoint_url,
            aws_access_key_id=config.access_key_id,
            aws_secret_access_key=config.secret_access_key,
            config=Config(signature_version="s3v4"),
            region_name=config.region,
        )
    return config, _CLIENT


def r2_enabled() -> bool:
    return _load_config() is not None


def upload_bytes(
    data: bytes, key: str, *, content_type: str | None = None
) -> bool:
    client_info = _get_client()
    if client_info is None:
        return False
    config, client = client_info
    extra_args = {"ContentType": content_type} if content_type else None
    if extra_args:
        client.put_object(Bucket=config.bucket_name, Key=key, Body=data, **extra_args)
    else:
        client.put_object(Bucket=config.bucket_name, Key=key, Body=data)
    return True


def upload_text(
    text: str, key: str, *, content_type: str = "text/plain; charset=utf-8"
) -> bool:
    return upload_bytes(text.encode("utf-8"), key, content_type=content_type)


def upload_html(html: str, key: str) -> bool:
    return upload_text(html, key, content_type="text/html; charset=utf-8")


def upload_json(payload: Any, key: str) -> bool:
    data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    return upload_bytes(
        data, key, content_type="application/json; charset=utf-8"
    )


def download_bytes(key: str) -> bytes | None:
    client_info = _get_client()
    if client_info is None:
        return None
    config, client = client_info
    try:
        response = client.get_object(Bucket=config.bucket_name, Key=key)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in {"NoSuchKey", "404"}:
            return None
        raise
    body = response.get("Body")
    if body is None:
        return None
    return body.read()


def download_text(key: str, *, encoding: str = "utf-8") -> str | None:
    data = download_bytes(key)
    if data is None:
        return None
    return data.decode(encoding)
