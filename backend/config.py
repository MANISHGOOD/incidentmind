"""Application configuration.

Everything is environment-driven so the same code runs in dev, on the demo
laptop, and against the docker-compose stack. See .env.example.
"""
from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ---- LLM ----
    groq_api_key: str = ""
    agent_model: str = "openai/gpt-oss-120b"

    # ---- Database ----
    database_url: str = "sqlite:///./incidentmind.db"

    # ---- Hindsight ----
    hindsight_base_url: str = "http://localhost:8888"
    hindsight_api_key: str = ""
    hindsight_bank_id: str = "incidentmind"
    memory_enabled: bool = True

    # ---- HTTP ----
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def sqlalchemy_url(self) -> str:
        """SQLAlchemy URL with the psycopg driver pinned for postgres URLs."""
        url = self.database_url
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+psycopg://", 1)
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
