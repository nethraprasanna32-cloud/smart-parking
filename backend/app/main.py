import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.app.routes.auth import router as auth_router
from backend.app.routes.camera import router as camera_router
from backend.app.routes.dashboard import router as dashboard_router
from backend.app.routes.models import router as models_router
from backend.app.routes.parking import router as parking_router
from backend.app.routes.plate_test import router as plate_test_router
from backend.app.routes.system import router as system_router
from backend.app.routes.vehicles import router as vehicles_router
from backend.app.services.auth import AuthMiddleware
from backend.app.state import auth, cameras, parking_system


logger = logging.getLogger("smart_parking")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SNAPSHOT_INTERVAL_SECONDS = int(os.getenv("SNAPSHOT_INTERVAL_SECONDS", "300"))


async def snapshot_loop():
    # Event-driven snapshots alone leave gaps overnight; the forecaster wants
    # an even series.
    while True:
        await asyncio.sleep(SNAPSHOT_INTERVAL_SECONDS)
        await run_in_threadpool(parking_system.record_snapshot)


@asynccontextmanager
async def lifespan(app):
    if not auth.enabled:
        logger.warning("DASHBOARD_PASSWORD is not set: anyone on the network can use the dashboard")

    logger.info("Storage: %s (%s)", parking_system.database.mode, parking_system.database.path)
    parking_system.seed_demo_data()
    task = asyncio.create_task(snapshot_loop())

    yield

    task.cancel()
    for camera in cameras.values():
        camera.stop()


app = FastAPI(
    title="Smart Parking System",
    description="Gate-camera parking occupancy, ALPR and access control",
    version="1.1.0",
    lifespan=lifespan,
)


app.add_middleware(AuthMiddleware, auth=auth)

# Wildcard CORS is only acceptable while the API is open. With a password set,
# only the dashboard's own origin (which carries the session cookie) is used.
if not auth.enabled:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"]
    )


app.include_router(parking_router)
app.include_router(vehicles_router)
app.include_router(dashboard_router)
app.include_router(models_router)
app.include_router(camera_router)
app.include_router(system_router)
app.include_router(auth_router)
app.include_router(plate_test_router)


@app.get("/api")
def api_info():
    return {
        "message": "Smart Parking System API",
        "storage": parking_system.database.mode,
        "vehicle_detection": parking_system.get_detection_model(),
        "forecast": parking_system.get_prediction_model(),
        "cameras": {gate: camera.state for gate, camera in cameras.items()},
        "auth_required": auth.enabled,
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "storage": parking_system.database.mode,
    }


class FrontendFiles(StaticFiles):
    """Browsers must check for a newer page, script or stylesheet on every load.

    Without this they guess a cache lifetime and keep running an old app.js
    against a new index.html after an update. Unchanged files still come back
    as a cheap 304.
    """

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


# Mounted last so API routes take precedence over the static catch-all.
frontend_directory = os.path.join(PROJECT_ROOT, "frontend")
if os.path.isdir(frontend_directory):
    app.mount(
        "/",
        FrontendFiles(directory=frontend_directory, html=True),
        name="frontend"
    )
