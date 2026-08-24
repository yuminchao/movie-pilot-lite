from datetime import UTC, datetime, timedelta

import pytest

from app.services.tokens import InvalidSourceToken, SourceTokenCodec


def test_source_token_round_trip() -> None:
    now = datetime(2026, 8, 23, tzinfo=UTC)
    codec = SourceTokenCodec(b"test-secret", clock=lambda: now)

    token = codec.encode(source_id="7", title="Movie")

    assert codec.decode(token) == {"source_id": "7", "title": "Movie"}


def test_source_token_expires() -> None:
    now = datetime(2026, 8, 23, tzinfo=UTC)
    codec = SourceTokenCodec(b"test-secret", ttl=timedelta(minutes=5), clock=lambda: now)
    token = codec.encode(source_id="7", title="Movie")
    expired_codec = SourceTokenCodec(
        b"test-secret",
        ttl=timedelta(minutes=5),
        clock=lambda: now + timedelta(minutes=6),
    )

    with pytest.raises(InvalidSourceToken):
        expired_codec.decode(token)


def test_source_token_rejects_tampering() -> None:
    now = datetime(2026, 8, 23, tzinfo=UTC)
    codec = SourceTokenCodec(b"test-secret", clock=lambda: now)
    token = codec.encode(source_id="7", title="Movie")
    tamper_index = len(token) // 2
    replacement = "A" if token[tamper_index] != "A" else "B"
    tampered_token = f"{token[:tamper_index]}{replacement}{token[tamper_index + 1:]}"

    with pytest.raises(InvalidSourceToken):
        codec.decode(tampered_token)
