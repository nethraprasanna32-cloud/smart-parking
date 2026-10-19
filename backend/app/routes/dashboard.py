import asyncio
import time
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from backend.app.state import parking_system


router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"]
)


class PredictionRequest(BaseModel):
    recent_occupancy: list[float] = Field(
        min_length=1,
        description="Recent readings, oldest first, assumed 5 minutes apart",
    )


class HistoryPoint(BaseModel):
    timestamp: str
    occupied: float


class PredictionTrainingRequest(BaseModel):
    history: Optional[list[HistoryPoint]] = Field(
        default=None,
        description="Omit to train on stored occupancy history",
    )
    epochs: int = Field(default=200, ge=1, le=5000)


def model_error(exc):
    if isinstance(exc, ValueError):
        return HTTPException(422, str(exc))
    return HTTPException(503, str(exc))


@router.get("/summary")
def dashboard_summary():
    return parking_system.summary()


@router.get("/occupancy-history")
def occupancy_history(
    limit: int = Query(default=96, ge=1, le=20000)
):
    return {
        "history": parking_system.database.get_occupancy_history(limit)
    }


@router.post("/prediction")
def predict_parking(request: PredictionRequest):
    now = datetime.now()
    count = len(request.recent_occupancy)
    history = [
        {
            "timestamp": (now - timedelta(minutes=5 * (count - 1 - index))).isoformat(),
            "occupied": value,
        }
        for index, value in enumerate(request.recent_occupancy)
    ]
    return parking_system.prediction.forecast(
        history,
        parking_system.parking.capacity,
        now=now
    )


@router.post("/prediction/train")
def train_prediction(request: Optional[PredictionTrainingRequest] = None):
    request = request or PredictionTrainingRequest()
    history = (
        [point.model_dump() for point in request.history]
        if request.history is not None
        else None
    )

    try:
        result = parking_system.train_prediction_model(history, epochs=request.epochs)
    except (ValueError, ImportError, FileNotFoundError) as exc:
        raise model_error(exc) from exc

    return {
        "status": "trained",
        "model": parking_system.get_prediction_model(),
        **result,
    }


@router.websocket("/ws")
async def dashboard_socket(websocket: WebSocket):
    """Push the summary whenever state changes (checked each second), or every 15 s."""
    await websocket.accept()
    sent_version = None
    sent_at = 0.0

    try:
        while True:
            stale = time.monotonic() - sent_at > 15
            if parking_system.state_version != sent_version or stale:
                summary = await run_in_threadpool(parking_system.summary)
                await websocket.send_json(summary)
                sent_version = summary["version"]
                sent_at = time.monotonic()
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass
