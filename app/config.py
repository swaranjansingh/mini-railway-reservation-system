import os
from functools import lru_cache
from pydantic import ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application configuration loaded from environment variables and optional .env file.
    """
    APP_NAME: str = "Mini Railway Reservation System"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # Database Settings
    DATABASE_URL: str = "sqlite:///./railway.db"

    # Security Settings
    JWT_SECRET_KEY: str = "development-insecure-secret-key-change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 15

    # Initial Admin Seed Credentials
    INITIAL_ADMIN_NAME: str = "System Administrator"
    INITIAL_ADMIN_EMAIL: str = "admin@railway.com"
    INITIAL_ADMIN_PASSWORD: str = "AdminSecurePassword123!"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str, info: ValidationInfo) -> str:
        env = (info.data.get("ENVIRONMENT") or os.getenv("ENVIRONMENT", "development")).lower()
        if env == "production":
            insecure_defaults = [
                "development-insecure-secret-key-change-me",
                "change_me_to_a_secure_random_key_in_production",
                "secret",
                "password",
            ]
            if len(v) < 32 or v.lower() in insecure_defaults:
                raise ValueError(
                    "In production, JWT_SECRET_KEY must be at least 32 characters and cryptographically random."
                )
        return v

    @field_validator("INITIAL_ADMIN_PASSWORD")
    @classmethod
    def validate_admin_password(cls, v: str, info: ValidationInfo) -> str:
        env = (info.data.get("ENVIRONMENT") or os.getenv("ENVIRONMENT", "development")).lower()
        if env == "production":
            insecure_defaults = [
                "AdminSecurePassword123!",
                "admin",
                "password",
                "admin123",
                "changeme",
            ]
            if len(v) < 12 or v in insecure_defaults:
                raise ValueError(
                    "In production, INITIAL_ADMIN_PASSWORD must be at least 12 characters "
                    "and not set to a known default password."
                )
        return v


@lru_cache()
def get_settings() -> Settings:
    """Return a cached singleton instance of application settings."""
    return Settings()

