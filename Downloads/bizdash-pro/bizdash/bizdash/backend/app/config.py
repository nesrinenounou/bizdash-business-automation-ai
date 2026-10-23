"""Single source of configuration (12-factor: everything comes from the environment)."""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    env: str = os.getenv("APP_ENV", "development")
    secret_key: str = os.getenv("SECRET_KEY", "dev-secret-change-me")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./dev.db")
    redis_url: str = os.getenv("REDIS_URL", "")
    upload_dir: str = os.getenv("UPLOAD_DIR", "./uploads")
    max_avatar_bytes: int = 2 * 1024 * 1024
    stats_ttl: int = 60
    login_max_failures: int = 5
    login_window: int = 300


settings = Settings()
