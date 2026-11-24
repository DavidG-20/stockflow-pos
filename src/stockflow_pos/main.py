"""FastAPI application entry point serving both the REST API and web dashboard."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from stockflow_pos import __version__
from stockflow_pos.core.config import settings
from stockflow_pos.core.database import Base, SessionLocal, engine
from stockflow_pos.core.seed import seed_initial_data
from stockflow_pos.models import entities as _entities  # noqa: F401
from stockflow_pos.routers.api import router as api_router

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Initialize database tables and optional demo seed data on startup."""
    Base.metadata.create_all(bind=engine)
    if settings.seed_demo_data and settings.app_env != "production":
        with SessionLocal() as db:
            seed_initial_data(db)
    yield


app = FastAPI(
    title=settings.app_name,
    version=__version__,
    description="Sistema Full-Stack de Inventario y Punto de Venta (POS) con JWT, control de caja y reportes.",
    lifespan=lifespan,
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next) -> Response:
    """Attach baseline HTTP security headers to every response."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    """Endpoint de salud del servicio."""
    return {"status": "ok", "service": settings.app_name, "version": __version__}


app.include_router(api_router)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def serve_frontend() -> FileResponse:
    """Serve the POS web dashboard."""
    return FileResponse(STATIC_DIR / "index.html")
