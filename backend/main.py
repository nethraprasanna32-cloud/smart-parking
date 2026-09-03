from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routes.parking import router as parking_router
from backend.routes.vehicles import router as vehicles_router
from backend.routes.dashboard import router as dashboard_router
from backend.routes.models import router as models_router
from backend.routes.camera import router as camera_router


app = FastAPI(
    title="Smart Parking System",
    description=(
        "AI-powered smart parking management "
        "and vehicle security system"
    ),
    version="1.0.0"
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


app.include_router(parking_router)
app.include_router(vehicles_router)
app.include_router(dashboard_router)
app.include_router(models_router)
app.include_router(camera_router)


@app.get("/")
def home():

    return {
        "message": "Smart Parking System API",
        "status": "running"
    }


@app.get("/health")
def health():

    return {
        "status": "healthy"
    }