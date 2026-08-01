from functools import lru_cache

from pydantic import AnyHttpUrl, Field, SecretStr, model_validator

from healthos_platform.config import BaseServiceSettings, Environment


class Settings(BaseServiceSettings):
    service_name: str = "healthos-api"
    database_url: SecretStr = SecretStr(
        "postgresql+asyncpg://healthos:change-me@localhost:5432/healthos"
    )
    redis_url: SecretStr = SecretStr("redis://localhost:6379/0")

    jwt_secret_key: SecretStr = SecretStr("local-development-secret-must-be-32-chars")
    jwt_refresh_secret_key: SecretStr = SecretStr("local-refresh-secret-must-also-be-32-chars")
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 30
    refresh_rotation_grace_seconds: int = 5
    jwt_issuer: str = "healthos"
    jwt_audience: str = "healthos-api"
    otp_secret_key: SecretStr = SecretStr("local-otp-secret-must-also-be-32-characters")
    otp_expire_minutes: int = 10
    otp_max_attempts: int = 5
    auth_cookie_secure: bool = False
    auth_cookie_domain: str | None = None
    allowed_hosts: list[str] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1", "testserver"]
    )
    access_cookie_name: str = "healthos_access"
    refresh_cookie_name: str = "healthos_refresh"
    csrf_cookie_name: str = "healthos_csrf"

    google_client_id: str = ""
    google_client_secret: SecretStr = SecretStr("")
    google_redirect_uri: AnyHttpUrl = Field(
        default=AnyHttpUrl("http://localhost:8000/api/v1/auth/google/callback")
    )
    frontend_auth_callback_url: AnyHttpUrl = Field(
        default=AnyHttpUrl("http://localhost:3000/auth/callback")
    )

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_from_email: str = ""
    smtp_use_tls: bool = True
    sms_webhook_url: str = ""
    sms_webhook_token: SecretStr = SecretStr("")

    document_max_bytes: int = 10_485_760
    ocr_api_url: str = ""
    ocr_api_key: SecretStr = SecretStr("")
    fhir_base_url: str = ""
    fhir_access_token: SecretStr = SecretStr("")
    insurance_api_url: str = ""
    insurance_api_key: SecretStr = SecretStr("")
    stripe_api_url: str = "https://api.stripe.com/v1"
    stripe_secret_key: SecretStr = SecretStr("")
    stripe_webhook_secret: SecretStr = SecretStr("")
    notification_webhook_url: str = ""
    job_watch_scan_interval_seconds: int = 300

    @model_validator(mode="after")
    def reject_placeholder_production_secret(self) -> "Settings":
        secrets = {
            "JWT_SECRET_KEY": self.jwt_secret_key.get_secret_value(),
            "JWT_REFRESH_SECRET_KEY": self.jwt_refresh_secret_key.get_secret_value(),
            "OTP_SECRET_KEY": self.otp_secret_key.get_secret_value(),
        }
        if self.environment == Environment.PRODUCTION:
            for name, value in secrets.items():
                normalized = value.lower()
                if "replace" in normalized or "local-" in normalized or len(value) < 32:
                    raise ValueError(f"{name} must be replaced with a production secret")
            if not self.auth_cookie_secure:
                raise ValueError("AUTH_COOKIE_SECURE must be true in production")
            if not self.smtp_host or not self.smtp_from_email:
                raise ValueError("SMTP delivery must be configured in production")
            if not self.sms_webhook_url:
                raise ValueError("SMS OTP delivery must be configured in production")
            if self.jwt_algorithm not in {"RS256", "ES256"}:
                raise ValueError("JWT_ALGORITHM must be RS256 or ES256 in production")
            if "ssl=require" not in self.database_url.get_secret_value():
                raise ValueError("DATABASE_URL must require TLS in production")
            if not self.redis_url.get_secret_value().startswith("rediss://"):
                raise ValueError("REDIS_URL must use TLS in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
