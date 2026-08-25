"""Run Alembic migrations from inside the running app.

Alembic's API is synchronous, so the app opens the connection itself and
hands it to `env.py` through `config.attributes`; `run_sync` bridges the two
worlds. Doing it this way keeps one engine and one set of SQLite pragmas
instead of letting Alembic open a second connection of its own.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

# apps/api/alembic.ini, three levels up from src/mecha_api/. That resolves
# for an editable install, which is how uv puts the workspace member on the
# path; a wheel installed into site-packages leaves the migrations behind,
# so deployments that build one must set MECHA_MIGRATE_ON_STARTUP=false and
# run `alembic upgrade head` from a checkout instead.
ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def _upgrade(connection: Connection) -> None:
    config = Config(str(ALEMBIC_INI))
    config.attributes["connection"] = connection
    command.upgrade(config, "head")


async def upgrade_to_head(engine: AsyncEngine) -> None:
    if not ALEMBIC_INI.is_file():
        raise RuntimeError(
            f"no alembic.ini at {ALEMBIC_INI} — migrate from a checkout and "
            "start with MECHA_MIGRATE_ON_STARTUP=false"
        )
    async with engine.begin() as connection:
        await connection.run_sync(_upgrade)
