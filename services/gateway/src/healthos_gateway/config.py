from functools import lru_cache

from pydantic import AnyHttpUrl, Field, SecretStr, model_validator

from healthos_platform.config import BaseServiceSettings, Environment


class Settings(BaseServiceSettings):
    service_name: str = "healthos-gateway"
    api_service_url: AnyHttpUrl = AnyHttpUrl("http://localhost:8000")
    ai_service_url: AnyHttpUrl = AnyHttpUrl("http://localhost:8001")
    upstream_timeout_seconds: float = 65.0
    redis_url: SecretStr = SecretStr("redis://localhost:6379/2")
    allowed_hosts: list[str] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1", "testserver", "gateway"]
    )
    rate_limit_per_minute: int = 300

    @model_validator(mode="after")
    def validate_gateway_security(self) -> "Settings":
        if self.environment == Environment.PRODUCTION:
            if not self.redis_url.get_secret_value().startswith("rediss://"):
                raise ValueError("REDIS_URL must use TLS in production")
            if "*" in self.allowed_hosts:
                raise ValueError("Wildcard hosts are forbidden in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
