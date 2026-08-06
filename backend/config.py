from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Keep the repository root as the single environment-file location even
    # when the backend is started from the backend/ directory.
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        extra="ignore",
    )

    app_name: str = "VaultVoice API"
    environment: str = "development"
    port: int = 8000
    database_url: str = "postgresql+psycopg://vaultvoice:vaultvoice@postgres:5432/vaultvoice"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-oss-20b:free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_site_url: str = "http://localhost:5173"
    openrouter_app_name: str = "VaultVoice"
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "vaultvoice-evidence"
    minio_secure: bool = False
    encryption_key: str = Field(default="", validation_alias="VAULTVOICE_ENCRYPTION_KEY")
    max_upload_bytes: int = 50 * 1024 * 1024
    rate_limit: str = "60/minute"
    commission_enabled: bool = False
    admin_api_token: str = Field(default="", validation_alias="VAULTVOICE_ADMIN_API_TOKEN")

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
