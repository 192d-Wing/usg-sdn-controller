"""FastAPI entry point."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from ..config import settings
from ..logging import configure_logging, log
from ..reconciler import Reconciler
from ..store import init_db
from .routes import auth, devices, intent, operations


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    await init_db()
    reconciler = Reconciler(settings.reconcile_interval_sec)
    if settings.reconcile_enabled:
        reconciler.start()
        log.info("reconciler-started", interval_sec=settings.reconcile_interval_sec)
    try:
        yield
    finally:
        await reconciler.stop()


app = FastAPI(
    title="usg-sdn-controller",
    version="0.1.0",
    description="Multi-vendor Campus EVPN controller (IPv6-only underlay, BGP-unnumbered, IS-IS).",
    lifespan=lifespan,
)

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(intent.router, prefix="/intent", tags=["intent"])
app.include_router(devices.router, prefix="/devices", tags=["devices"])
app.include_router(operations.router, prefix="/operations", tags=["operations"])


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}
