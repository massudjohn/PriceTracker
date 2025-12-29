from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from .background.tasks import queue_periodic_fetches
from .routes import router

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Price Tracker API", version="0.1.0")
app.include_router(router, prefix="/api")


@app.get("/")
async def root():
    """Redirect root to the dashboard."""
    return RedirectResponse(url="/api/")


@app.on_event("startup")
async def configure_workers() -> None:
    # Kick off periodic fetching if Redis is available. Failures are logged
    # but should not crash the application during development.
    queue_periodic_fetches()
