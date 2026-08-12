import base64
import hashlib
import hmac
import json
from collections.abc import Mapping
from typing import Any

from .errors import InvalidQueryError


CURSOR_VERSION = 1
MAX_CURSOR_LENGTH = 4096
_CHECKSUM_LENGTH = hashlib.sha256().digest_size


def query_fingerprint(values: Mapping[str, object]) -> str:
    payload = json.dumps(
        values,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def encode_cursor(payload: Mapping[str, object]) -> str:
    versioned_payload = {
        "version": CURSOR_VERSION,
        **payload,
    }
    encoded_payload = json.dumps(
        versioned_payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    checksum = hashlib.sha256(encoded_payload).digest()
    token = base64.urlsafe_b64encode(
        encoded_payload + checksum
    ).rstrip(b"=")
    return token.decode("ascii")


def decode_cursor(cursor: str) -> dict[str, Any]:
    if not isinstance(cursor, str) or not cursor:
        raise InvalidQueryError("cursor must be non-empty")
    if len(cursor) > MAX_CURSOR_LENGTH:
        raise InvalidQueryError("cursor is too long")

    try:
        padding = "=" * (-len(cursor) % 4)
        packet = base64.b64decode(
            cursor + padding,
            altchars=b"-_",
            validate=True,
        )
        canonical_cursor = base64.urlsafe_b64encode(packet).rstrip(b"=")
        if canonical_cursor.decode("ascii") != cursor:
            raise ValueError
        if len(packet) <= _CHECKSUM_LENGTH:
            raise ValueError
        encoded_payload = packet[:-_CHECKSUM_LENGTH]
        checksum = packet[-_CHECKSUM_LENGTH:]
        if not hmac.compare_digest(
            checksum,
            hashlib.sha256(encoded_payload).digest(),
        ):
            raise ValueError
        payload = json.loads(encoded_payload)
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        raise InvalidQueryError("cursor is malformed") from error

    if not isinstance(payload, dict):
        raise InvalidQueryError("cursor is malformed")
    if payload.get("version") != CURSOR_VERSION:
        raise InvalidQueryError("cursor version is not supported")
    return payload
