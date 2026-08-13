import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.core.config import settings
from app.services import scheduler
from app.routers import (
    users, farms, cows, inseminations, needling, checks, calving,
    reports, vets, vaccinations, notifications, admin, imports, bulls,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("app")

@asynccontextmanager
async def lifespan(_: FastAPI):
    """Run the lifecycle sweep on a timer for as long as the API is up.

    Without this the day-223 dry-off (and every other timed transition) only
    happened when somebody opened a report, so a quiet day silently skipped it.
    """
    scheduler.start()
    try:
        yield
    finally:
        await scheduler.stop()


app = FastAPI(title="Major Dairy AI API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Paging metadata is useless to a browser client unless it is exposed.
    expose_headers=["X-Total-Count"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Log every unhandled error with request context, return a clean 500.

    Without this, tracebacks are easy to miss and clients get an opaque error.
    """
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Log server-side (5xx) HTTP errors; 4xx are expected and left quiet."""
    if exc.status_code >= 500:
        logger.error("%s %s → %s: %s", request.method, request.url.path, exc.status_code, exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

app.include_router(users.router,          prefix="/users",          tags=["users"])
app.include_router(farms.router,          prefix="/farms",          tags=["farms"])
app.include_router(cows.router,           prefix="/cows",           tags=["cows"])
app.include_router(inseminations.router,  prefix="/inseminations",  tags=["inseminations"])
app.include_router(needling.router,       prefix="/needling",       tags=["needling"])
app.include_router(checks.router,         prefix="/checks",         tags=["checks"])
app.include_router(calving.router,        prefix="/calving",        tags=["calving"])
app.include_router(vaccinations.router,   prefix="/vaccinations",   tags=["vaccinations"])
app.include_router(reports.router,        prefix="/reports",        tags=["reports"])
app.include_router(vets.router,           prefix="/vets",           tags=["vets"])
app.include_router(notifications.router,  prefix="/notifications",  tags=["notifications"])
app.include_router(admin.router,          prefix="/admin",          tags=["admin"])
app.include_router(imports.router,        prefix="/imports",        tags=["imports"])
app.include_router(bulls.router,          prefix="/bulls",          tags=["bulls"])


@app.get("/health")
async def health():
    return {"status": "ok"}
