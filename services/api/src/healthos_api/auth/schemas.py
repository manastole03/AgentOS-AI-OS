from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
)

from healthos_api.db.models import AccountType, OtpPurpose, UserStatus

Password = Annotated[str, StringConstraints(min_length=12, max_length=128)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Phone = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=7, max_length=32, pattern=r"^\+?[0-9() .-]+$"
    ),
]


class PasswordMixin(BaseModel):
    password: Password

    @field_validator("password")
    @classmethod
    def reject_common_passwords(cls, value: str) -> str:
        if value.casefold() in {
            "password1234",
            "administrator",
            "qwerty123456",
            "letmein123456",
        }:
            raise ValueError("Choose a less common password")
        return value


class PatientSignup(PasswordMixin):
    email: EmailStr
    first_name: ShortText
    last_name: ShortText
    phone: Phone
    date_of_birth: date | None = None
    sex_at_birth: Annotated[
        str | None, StringConstraints(strip_whitespace=True, min_length=1, max_length=32)
    ] = None
    blood_type: Annotated[
        str | None, StringConstraints(strip_whitespace=True, min_length=1, max_length=8)
    ] = None
    emergency_contact: Annotated[
        str | None, StringConstraints(strip_whitespace=True, min_length=2, max_length=255)
    ] = None


class DoctorSignup(PatientSignup):
    license_number: ShortText
    license_jurisdiction: ShortText | None = None
    specialty: ShortText | None = None
    affiliation: Annotated[
        str | None, StringConstraints(strip_whitespace=True, min_length=2, max_length=255)
    ] = None


class OrganizationSignup(PasswordMixin):
    email: EmailStr
    legal_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=2, max_length=255)
    ]
    registration_number: ShortText
    phone: Phone
    license_number: ShortText | None = None
    organization_type: ShortText | None = None
    product_types: list[ShortText] = Field(default_factory=list, max_length=20)


class LoginRequest(PasswordMixin):
    email: EmailStr


class OtpVerificationRequest(BaseModel):
    email: EmailStr
    code: Annotated[str, StringConstraints(pattern=r"^[0-9]{6}$")]
    purpose: OtpPurpose = OtpPurpose.EMAIL_VERIFICATION


class OtpResendRequest(BaseModel):
    email: EmailStr
    purpose: OtpPurpose = OtpPurpose.EMAIL_VERIFICATION


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(PasswordMixin):
    email: EmailStr
    code: Annotated[str, StringConstraints(pattern=r"^[0-9]{6}$")]


class MessageResponse(BaseModel):
    message: str
    debug_code: str | None = None
    debug_mobile_code: str | None = None


class UserSummary(BaseModel):
    id: UUID
    email: EmailStr
    account_type: AccountType
    status: UserStatus
    email_verified: bool
    phone_verified: bool
    roles: list[str]
    patient_id: str | None = None
    tenant_id: UUID | None = None


class AuthResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105
    expires_in: int
    user: UserSummary


class ProfileResponse(UserSummary):
    first_name: str | None = None
    last_name: str | None = None
    legal_name: str | None = None
    license_number: str | None = None
    registration_number: str | None = None
    phone: str | None = None
    date_of_birth: date | None = None
    sex_at_birth: str | None = None
    blood_type: str | None = None
    emergency_contact: str | None = None
    specialty: str | None = None
    affiliation: str | None = None
    license_jurisdiction: str | None = None
    organization_type: str | None = None
    product_types: list[str] = Field(default_factory=list)
    credentials_verified: bool | None = None
    avatar_url: str | None = None
    created_at: datetime
    updated_at: datetime


class ProfileUpdate(BaseModel):
    first_name: ShortText | None = None
    last_name: ShortText | None = None
    legal_name: Annotated[
        str | None, StringConstraints(strip_whitespace=True, min_length=2, max_length=255)
    ] = None
    phone: Phone | None = None
    avatar_url: AnyHttpUrl | None = None


class SessionResponse(BaseModel):
    id: UUID
    user_agent: str | None
    ip_address: str | None
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime
    current: bool


class GoogleAccountType(BaseModel):
    account_type: AccountType
