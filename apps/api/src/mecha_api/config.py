"""App settings, read from the environment (and `apps/api/.env` in dev).

Every variable uses the ``MECHA_`` prefix — see `.env.example`.

Split by owner, because each is read at a different moment. `AgentSettings`
is the only one with a required field, so it is read at startup and fails
fast; the other two have full defaults and are read wherever they are needed
— tracing at import, the database URL from Alembic's `env.py` as well as the
app, so a migration never needs a model string set.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_CONFIG = SettingsConfigDict(env_prefix="MECHA_", env_file=".env", extra="ignore")


class AgentSettings(BaseSettings):
    model_config = _CONFIG

    model: str = Field(
        description=(
            'Pydantic AI model string, "<provider>:<model>" — e.g. '
            '"anthropic:claude-sonnet-4-6" or "openai:gpt-5.2". The matching '
            "provider key (ANTHROPIC_API_KEY / OPENAI_API_KEY) must be set too."
        ),
    )


class DatabaseSettings(BaseSettings):
    model_config = _CONFIG

    database_url: str = Field(
        default="sqlite+aiosqlite:///mecha.db",
        description=(
            "SQLAlchemy async URL. Relative SQLite paths resolve against "
            "apps/api. Postgres needs asyncpg installed: "
            '"postgresql+asyncpg://user:pass@host/db".'
        ),
    )
    migrate_on_startup: bool = Field(
        default=True,
        description=(
            "Run `alembic upgrade head` when the app starts. Convenient for "
            "one process; turn it off where several replicas start at once "
            "and migrate from a release step instead."
        ),
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
