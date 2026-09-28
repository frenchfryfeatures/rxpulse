from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: Literal["local", "test", "staging", "production"] = "local"
    database_url: str = "postgresql+asyncpg://rxpulse:rxpulse@localhost:5432/rxpulse"
    cors_origins: list[str] = ["http://localhost:3000"]

    # "entra" validates Microsoft Entra ID access tokens issued via MSAL.
    # "dev" accepts tokens minted by /api/v1/dev/token (local development and tests only).
    auth_mode: Literal["entra", "dev"] = "entra"
    azure_tenant_id: str = ""
    azure_api_client_id: str = ""
    allowed_tenants: list[str] = []
    required_scope: str = "access_as_user"
    super_admin_app_role: str = "RxPulse.SuperAdmin"
    jwt_leeway_seconds: int = 60

    # Pharmacy rules
    pharmacy_location_code: str = "MAIN-PHARMACY"
    min_shelf_life_days: int = 30

    @model_validator(mode="after")
    def _check(self) -> "Settings":
        if self.auth_mode == "dev" and self.env in ("staging", "production"):
            raise ValueError("AUTH_MODE=dev is not allowed in staging/production")
        if self.auth_mode == "entra" and self.env != "test":
            missing = [n for n in ("azure_tenant_id", "azure_api_client_id") if not getattr(self, n)]
            if missing:
                raise ValueError(f"AUTH_MODE=entra requires: {', '.join(m.upper() for m in missing)}")
        if not self.allowed_tenants and self.azure_tenant_id:
            self.allowed_tenants = [self.azure_tenant_id]
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
