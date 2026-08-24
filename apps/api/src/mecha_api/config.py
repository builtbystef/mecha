"""App settings, read from the environment (and `apps/api/.env` in dev).

Every variable uses the ``MECHA_`` prefix — see `.env.example`.
"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MECHA_", env_file=".env", extra="ignore"
    )

    model: str = Field(
        description=(
            'Pydantic AI model string, "<provider>:<model>" — e.g. '
            '"anthropic:claude-sonnet-4-6" or "openai:gpt-5.2". The matching '
            "provider key (ANTHROPIC_API_KEY / OPENAI_API_KEY) must be set too."
        ),
    )
    database_path: Path = Field(
        default=Path("mecha.db"),
        description="SQLite file for the conversation store.",
    )
