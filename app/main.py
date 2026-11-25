from contextlib import asynccontextmanager
from typing import Any, Dict
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, text

from app.config import get_settings
from app.database import engine, init_db
from app.routers import (
    auth_router,
    users_router,
    admin_router,
    stations_router,
    trains_router,
    bookings_router,
)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.
    Initializes database tables on startup.
    """
    init_db()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "A robust, secure, and clean FastAPI backend for a Railway Reservation Platform. "
        "Supports passenger accounts, administrative train/route management, "
        "intermediate-station train searches, interval-based seat occupancy, "
        "and concurrency-safe booking with PNR generation."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Enable CORS for development/testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Routers
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(admin_router)
app.include_router(stations_router)
app.include_router(trains_router)
app.include_router(bookings_router)


@app.get(
    "/",
    tags=["General"],
    summary="Root endpoint - System Overview",
)
def root() -> Dict[str, Any]:
    """
    Root endpoint returning service identity and link to documentation.
    """
    return {
        "name": settings.APP_NAME,
        "version": "1.0.0",
        "status": "online",
        "documentation": "/docs",
        "environment": settings.ENVIRONMENT,
    }


@app.get(
    "/health",
    tags=["General"],
    summary="Health check endpoint",
)
def health_check() -> Dict[str, Any]:
    """
    Service health check verifying application and database connectivity.
    """
    db_status = "connected"
    try:
        with Session(engine) as session:
            session.exec(text("SELECT 1")).first()
    except Exception:
        db_status = "unavailable"

    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "database": db_status,
        "environment": settings.ENVIRONMENT,
    }
