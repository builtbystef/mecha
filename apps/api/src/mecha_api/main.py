from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from pydantic import BaseModel

from mecha_api import chat
from mecha_api.config import Settings
from mecha_api.store import ConversationStore


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Fails fast on missing MECHA_MODEL — see apps/api/.env.example.
    settings = Settings()
    store = ConversationStore(settings.database_path)
    await store.connect()
    async with httpx.AsyncClient(timeout=httpx.Timeout(15)) as http_client:
        app.state.settings = settings
        app.state.store = store
        app.state.http_client = http_client
        try:
            yield
        finally:
            await store.close()


app = FastAPI(title="mecha-api", lifespan=lifespan)
app.include_router(chat.router)


class Health(BaseModel):
    status: str


@app.get("/api/health", operation_id="getHealth")
def get_health() -> Health:
    return Health(status="ok")
