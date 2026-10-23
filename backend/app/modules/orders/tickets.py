"""Коды билетов для QR. Код подписан HMAC секретом сервера: подделать билет, не зная
секрета, нельзя, а проверить его можно без похода в БД."""

import base64
import hashlib
import hmac
import uuid

from app.core.config import settings

PREFIX = "TB1"


def _signature(ticket_id: uuid.UUID) -> str:
    digest = hmac.new(settings.secret_key.encode(), ticket_id.bytes, hashlib.sha256).digest()
    return base64.b32encode(digest[:10]).decode().rstrip("=")


def make_code(ticket_id: uuid.UUID) -> str:
    return f"{PREFIX}.{ticket_id.hex}.{_signature(ticket_id)}"


def parse_code(code: str) -> uuid.UUID | None:
    """id билета, если подпись верна; иначе None."""
    try:
        prefix, ticket_hex, signature = code.strip().split(".")
        ticket_id = uuid.UUID(hex=ticket_hex)
    except ValueError:
        return None
    if prefix != PREFIX or not hmac.compare_digest(signature, _signature(ticket_id)):
        return None
    return ticket_id
