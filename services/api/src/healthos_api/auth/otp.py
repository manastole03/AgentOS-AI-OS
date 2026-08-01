import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from healthos_api.config import Settings
from healthos_api.db.models import OtpChallenge, OtpPurpose


def generate_otp_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp(*, email: str, purpose: OtpPurpose, code: str, settings: Settings) -> str:
    message = f"{email.strip().lower()}:{purpose.value}:{code}".encode()
    return hmac.new(
        settings.otp_secret_key.get_secret_value().encode(), message, hashlib.sha256
    ).hexdigest()


def new_otp_challenge(
    *, email: str, purpose: OtpPurpose, settings: Settings, user_id: UUID | None = None
) -> tuple[OtpChallenge, str]:
    code = generate_otp_code()
    challenge = OtpChallenge(
        user_id=user_id,
        email=email.strip().lower(),
        purpose=purpose,
        code_hash=hash_otp(email=email, purpose=purpose, code=code, settings=settings),
        max_attempts=settings.otp_max_attempts,
        expires_at=datetime.now(UTC) + timedelta(minutes=settings.otp_expire_minutes),
    )
    return challenge, code


def otp_matches(challenge: OtpChallenge, code: str, settings: Settings) -> bool:
    supplied_hash = hash_otp(
        email=challenge.email,
        purpose=challenge.purpose,
        code=code,
        settings=settings,
    )
    return hmac.compare_digest(challenge.code_hash, supplied_hash)
