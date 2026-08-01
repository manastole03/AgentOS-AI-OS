from uuid import uuid4

import pytest
from pydantic import ValidationError

from healthos_api.auth.identifiers import generate_patient_id
from healthos_api.auth.otp import new_otp_challenge, otp_matches
from healthos_api.auth.passwords import hash_password, verify_password
from healthos_api.auth.tokens import create_access_token, decode_access_token
from healthos_api.config import Settings
from healthos_api.db.models import OtpPurpose
from healthos_platform.config import Environment, LogFormat


def test_access_token_round_trip() -> None:
    settings = Settings(environment=Environment.TEST)
    user_id = uuid4()
    session_id = uuid4()

    token = create_access_token(
        user_id=user_id,
        session_id=session_id,
        token_version=3,
        roles=["patient"],
        permissions=["profile:read"],
        settings=settings,
    )
    claims = decode_access_token(token, settings)

    assert claims.sub == user_id
    assert claims.sid == session_id
    assert claims.ver == 3
    assert claims.roles == ["patient"]


def test_passwords_use_one_way_hashes() -> None:
    encoded = hash_password("correct horse battery staple")

    assert encoded != "correct horse battery staple"
    assert verify_password("correct horse battery staple", encoded)
    assert not verify_password("incorrect password", encoded)


def test_otp_is_hashed_and_verifiable() -> None:
    settings = Settings(environment=Environment.TEST)
    challenge, code = new_otp_challenge(
        email="patient@example.com",
        purpose=OtpPurpose.EMAIL_VERIFICATION,
        settings=settings,
        user_id=uuid4(),
    )

    assert challenge.code_hash != code
    assert otp_matches(challenge, code, settings)
    assert not otp_matches(challenge, "000000" if code != "000000" else "999999", settings)


def test_patient_ids_are_exactly_fifteen_characters() -> None:
    identifiers = {generate_patient_id() for _ in range(100)}

    assert len(identifiers) == 100
    assert all(identifier.startswith("PAT") and len(identifier) == 15 for identifier in identifiers)


def test_production_rejects_placeholder_jwt_secret() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY"):
        Settings(
            environment=Environment.PRODUCTION,
            log_format=LogFormat.JSON,
            jwt_secret_key="replace-this-placeholder-secret-value",
        )
