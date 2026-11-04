"""Unit tests for MediaTokenService."""

from vizenlink_nvr.services.media_token import MediaTokenService


def test_media_token_generate_and_verify() -> None:
    """Verify that a valid token parses and matches user, serial, and stream."""
    service = MediaTokenService(b"test-secret-key-32-bytes-long!")
    token = service.generate_token(user_id=42, camera_serial="CAM-1234", stream="sub", ttl_seconds=300)

    assert isinstance(token, str)
    assert "." in token

    payload = service.verify_token(token)
    assert payload is not None
    assert payload["sub"] == 42
    assert payload["serial"] == "CAM-1234"
    assert payload["stream"] == "sub"
    assert "exp" in payload
    assert "nonce" in payload


def test_media_token_tampered_signature() -> None:
    """Verify that a tampered signature fails verification."""
    service = MediaTokenService(b"test-secret-key-32-bytes-long!")
    token = service.generate_token(user_id=1, camera_serial="CAM-1", stream="main")

    payload_b64, sig_b64 = token.split(".")
    tampered_token = f"{payload_b64}.tamperedSig123"

    assert service.verify_token(tampered_token) is None


def test_media_token_tampered_payload() -> None:
    """Verify that altering the payload fails verification."""
    service = MediaTokenService(b"test-secret-key-32-bytes-long!")
    token = service.generate_token(user_id=1, camera_serial="CAM-1", stream="main")

    _, sig_b64 = token.split(".")
    # Forge a different payload
    fake_token = f"eyJzZXJpYWwiOiJDQU0tMiJ9.{sig_b64}"

    assert service.verify_token(fake_token) is None


def test_media_token_expired() -> None:
    """Verify that an expired token returns None."""
    service = MediaTokenService(b"test-secret-key-32-bytes-long!")
    # Negative TTL = immediately expired
    token = service.generate_token(user_id=1, camera_serial="CAM-1", stream="sub", ttl_seconds=-10)

    assert service.verify_token(token) is None


def test_media_token_malformed_inputs() -> None:
    """Verify that empty or malformed strings return None without raising."""
    service = MediaTokenService()
    assert service.verify_token("") is None
    assert service.verify_token("invalid") is None
    assert service.verify_token("a.b.c") is None
    assert service.verify_token(".") is None
