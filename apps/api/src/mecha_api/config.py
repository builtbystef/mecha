"""App settings, read from the environment (and `apps/api/.env` in dev).

Every variable uses the ``MECHA_`` prefix — see `.env.example`.

Two classes, because they are read at different times. `ObservabilitySettings`
has no required field, so tracing can be set up at import; `Settings` requires
a model and is read at startup, late enough that the schema export and the
resulting failure are both traced.
"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_CONFIG = SettingsConfigDict(env_prefix="MECHA_", env_file=".env", extra="ignore")


class Settings(BaseSettings):
    model_config = _CONFIG

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


class ObservabilitySettings(BaseSettings):
    model_config = _CONFIG

    service_name: str = Field(
        default="mecha-api",
        description="`service.name` on exported spans.",
    )
    environment: str = Field(
        default="development",
        description='Deployment environment tag on spans — e.g. "production".',
    )
    trace_content: bool = Field(
        default=True,
        description=(
            "Attach prompts and model replies to spans. Turn off where "
            "conversations carry data that must not leave the process."
        ),
    )
    trace_console: bool = Field(
        default=False,
        description="Also print spans to the console. Verbose; for debugging.",
    )
    log_level: str = Field(
        default="INFO",
        description="Root log level, e.g. DEBUG / INFO / WARNING.",
    )
