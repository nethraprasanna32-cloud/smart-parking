from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.app.services.alerts import ALERT_KINDS
from backend.app.services.reports import daily_report, summarize
from backend.app.state import parking_system


router = APIRouter(tags=["System"])


class SettingsRequest(BaseModel):
    event_cooldown_seconds: Optional[int] = Field(default=None, ge=0, le=3600)
    min_camera_reads: Optional[int] = Field(default=None, ge=1, le=10)
    admit_visitors: Optional[bool] = None
    plate_region: Optional[Literal["IN", "ANY"]] = None
    alert_kinds: Optional[list[str]] = Field(default=None, description=f"Any of {', '.join(ALERT_KINDS)}")


class BarrierRequest(BaseModel):
    reason: str = Field(default="manual", max_length=40)


@router.get("/settings")
def get_settings():
    return parking_system.get_settings()


@router.post("/settings")
def update_settings(request: SettingsRequest):
    try:
        return parking_system.update_settings(**request.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/barrier/{gate}/open")
def open_barrier(gate: Literal["entry", "exit"], request: Optional[BarrierRequest] = None):
    """Operator override: open the barrier without a plate event."""
    reason = (request or BarrierRequest()).reason
    record = parking_system.barrier.open(gate, reason=reason, wait=True)
    parking_system.bump()
    return record


@router.get("/alerts")
def get_alerts():
    return parking_system.alerts.status()


@router.post("/alerts/test")
def send_test_alert():
    alerts = parking_system.alerts
    if not alerts.channels():
        raise HTTPException(
            400,
            "No alert channel is set up. Set ALERT_WEBHOOK_URL or the SMTP_* variables and restart.",
        )
    return alerts.send("test", "Test alert", "Smart Parking alerts are working.", wait=True)


@router.get("/reports/daily")
def get_daily_report(days: int = Query(default=7, ge=1, le=90)):
    rows = daily_report(parking_system.database, days=days)
    return {"days": rows, "totals": summarize(rows)}
