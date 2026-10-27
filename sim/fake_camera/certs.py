"""Certificate generation for fake camera TLS simulation."""

import hashlib
from datetime import UTC, datetime

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec


def generate_self_signed_cert() -> tuple[bytes, bytes, str]:
    """Generate self-signed EC certificate with an already-expired validity window."""
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, "localhost")])

    # Already-expired validity window to mirror SR-11 (e.g. 2020 to 2021)
    not_valid_before = datetime(2020, 1, 1, 0, 0, 0, tzinfo=UTC)
    not_valid_after = datetime(2021, 1, 1, 0, 0, 0, tzinfo=UTC)

    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_valid_before)
        .not_valid_after(not_valid_after)
        .sign(key, hashes.SHA256())
    )

    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    cert_der = cert.public_bytes(serialization.Encoding.DER)
    fingerprint = hashlib.sha256(cert_der).hexdigest()

    return cert_pem, key_pem, fingerprint
