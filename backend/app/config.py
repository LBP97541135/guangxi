"""应用配置。所有可变值来自环境变量，业务代码不得散落硬编码配置。"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: str = "dev"
    database_url: str = "sqlite:///./guangxi.db"
    questions_file: Path = Path("config/questions.json")
    prompt_file: Path = Path("config/prompt.txt")

    model_provider: Literal["fake", "real"] = "fake"
    model_api_key: str | None = None
    model_base_url: str | None = None
    model_name: str | None = None
    model_timeout_seconds: float = 15.0
    model_reasoning_effort: str | None = None

    quote_max_chars: int = 50
    answer_max_chars: int = 500

    allow_cors_origins: str = "*"

    @field_validator("database_url")
    @classmethod
    def _validate_database_url(cls, value: str) -> str:
        if not (value.startswith("sqlite") or value.startswith("postgresql")):
            raise ValueError("DATABASE_URL 仅支持 sqlite:// 或 postgresql:// 前缀")
        return value

    @field_validator("model_timeout_seconds", "quote_max_chars", "answer_max_chars")
    @classmethod
    def _validate_positive(cls, value, info):
        if value <= 0:
            raise ValueError(f"{info.field_name} 必须为正数")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
