from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="mecha-api")


class Health(BaseModel):
    status: str


class Greeting(BaseModel):
    message: str


@app.get("/api/health", operation_id="getHealth")
def get_health() -> Health:
    return Health(status="ok")


@app.get("/api/hello/{name}", operation_id="getGreeting")
def get_greeting(name: str) -> Greeting:
    return Greeting(message=f"Hello, {name}!")
