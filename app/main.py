from __future__ import annotations

from contextlib import asynccontextmanager
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles

from app.api.routes.listings import router as listings_router
from app.config import get_settings
from app.harness.bootstrap import bootstrap_database
from app.participant.description_analysis import _get_model


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    bootstrap_database(db_path=settings.db_path, raw_data_dir=settings.raw_data_dir)
    _get_model()  # preload embedding model so first request is fast
    yield


app = FastAPI(
    title="Datathon 2026 Listings Harness",
    lifespan=lifespan,
)

allowed_origins = [
    origin.strip()
    for origin in os.getenv("API_ALLOWED_ORIGINS", "*").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins or ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(listings_router)

_sred_images_dir = get_settings().raw_data_dir / "sred_images"
if _sred_images_dir.exists():
    app.mount(
        "/raw-data-images",
        StaticFiles(directory=str(_sred_images_dir)),
        name="raw-data-images",
    )
