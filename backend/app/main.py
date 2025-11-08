from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse, Response

from .auth import hash_password
from .auth_routes import router as auth_router
from .config import settings
from .database import SessionLocal, engine
from .models import Base, UserRole
from .routers import router
from .workers import create_channel_worker


Base.metadata.create_all(bind=engine)


def _ensure_default_admin() -> None:
    db = SessionLocal()
    try:
        if db.get_user_by_email(settings.default_admin_email) is None:
            db.create_user(
                settings.default_admin_email,
                hash_password(settings.default_admin_password),
                UserRole.ADMIN,
            )
    finally:
        db.close()


_ensure_default_admin()

channel_worker = create_channel_worker(settings.background_poll_interval_seconds)
channel_worker.start()

app = FastAPI(title="Dauda Channel Manager")

base_frontend = Path(__file__).parent / "frontend"
templates_dir = base_frontend / "templates"
static_dir = base_frontend / "static"
icons_dir = static_dir / "icons"
service_worker_file = base_frontend / "service-worker.js"
manifest_file = base_frontend / "manifest.json"

app.include_router(auth_router)
app.include_router(router)


def _read_text(path: Path) -> str:
    if not path.exists():
        raise HTTPException(status_code=404)
    return path.read_text(encoding="utf-8")


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _read_text(templates_dir / "index.html")


@app.get("/static/css/styles.css", response_class=PlainTextResponse)
def styles() -> str:
    return _read_text(static_dir / "css" / "styles.css")


@app.get("/static/js/app.js", response_class=PlainTextResponse)
def app_script() -> str:
    return _read_text(static_dir / "js" / "app.js")


@app.get("/manifest.webmanifest", response_class=PlainTextResponse)
def manifest() -> str:
    return _read_text(manifest_file)


@app.get("/service-worker.js", response_class=PlainTextResponse)
def service_worker() -> str:
    return _read_text(service_worker_file)


@app.get("/static/icons/app-icon.svg")
def app_icon() -> Response:
    svg = _read_text(icons_dir / "app-icon.svg")
    return Response(content=svg, media_type="image/svg+xml")


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
