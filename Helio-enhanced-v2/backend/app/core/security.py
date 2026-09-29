"""Password hashing and contact-detail validation for patient accounts.

Uses only the standard library (PBKDF2-HMAC-SHA256) so no new dependency is
needed. Stored format: ``pbkdf2$<iterations>$<salt hex>$<hash hex>``.
"""
import hashlib
import hmac
import os
import re

_ITERATIONS = 200_000
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return f"pbkdf2${_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        scheme, iterations, salt_hex, hash_hex = stored.split("$")
        if scheme != "pbkdf2":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", (password or "").encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(digest.hex(), hash_hex)
    except (ValueError, TypeError):
        return False


def normalize_contact(value: str) -> tuple[str, str]:
    """Return ``("email" | "phone", normalised value)`` or raise ValueError.

    Emails are lower-cased. Phone numbers keep an optional leading ``+`` and
    digits only (spaces, dashes and brackets are stripped), 7-15 digits.
    """
    raw = (value or "").strip()
    if not raw:
        raise ValueError("Enter an email address or phone number.")

    if "@" in raw:
        email = raw.lower()
        if not _EMAIL_RE.match(email) or len(email) > 120:
            raise ValueError("Enter a valid email address.")
        return "email", email

    digits = re.sub(r"[\s\-().]", "", raw)
    plus = digits.startswith("+")
    body = digits[1:] if plus else digits
    if not body.isdigit() or not 7 <= len(body) <= 15:
        raise ValueError("Enter a valid phone number (7-15 digits).")
    return "phone", ("+" if plus else "") + body
