from __future__ import annotations

from fastapi import FastAPI

from .database import engine
from .models import Base
from .routers import router


Base.metadata.create_all(bind=engine)

app = FastAPI(title="Dauda Channel Manager")
app.include_router(router)


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
