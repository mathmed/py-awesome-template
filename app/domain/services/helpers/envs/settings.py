from enum import StrEnum
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: Environment = Environment.DEVELOPMENT
    app_name: str = "Awesome Python Template"
    log_level: str = "INFO"
    # JSON list, e.g. CORS_ORIGINS='["http://localhost:3000"]'
    cors_origins: list[str] = []

    @property
    def is_production(self) -> bool:
        return self.env == Environment.PRODUCTION


@lru_cache
def get_settings() -> Settings:
    return Settings()
