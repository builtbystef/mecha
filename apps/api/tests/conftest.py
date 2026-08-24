from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from mecha_api.main import app
from pydantic_ai import models

# No test may ever hit a real LLM provider.
models.ALLOW_MODEL_REQUESTS = False


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("MECHA_MODEL", "test")
    monkeypatch.setenv("MECHA_DATABASE_PATH", str(tmp_path / "test.db"))
    # Context manager so the lifespan (store + http client) runs.
    with TestClient(app) as test_client:
        yield test_client
