from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, Literal
from functools import lru_cache


class Settings(BaseSettings):
    # Application
    APP_ENV: Literal["development", "testing", "production"] = "development"
    LOG_LEVEL: str = "INFO"

    # Database
    DATABASE_URL: str

    # Storage
    STORAGE_BACKEND: Literal["local", "s3"] = "local"
    STORAGE_LOCAL_PATH: str = "./storage"

    # S3 settings
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_STORAGE_BUCKET_NAME: Optional[str] = None
    AWS_S3_ENDPOINT_URL: Optional[str] = None
    AWS_REGION: str = "us-east-1"

    # Validation settings
    VALIDATION_AUTO_APPROVE_THRESHOLD: int = 85

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()