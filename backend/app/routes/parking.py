import csv
import io
from datetime import date, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ai_pipeline.detect_and_ocr import normalize_plate
from backend.app.state import parking_system


router = APIRouter(
    tags=["Parking"]
)


class CapacityRequest(BaseModel):
    capacity: int = Field(ge=0, le=500)


class ManualEventRequest(BaseModel):
    plate_number: str = Field(min_length=1, max_length=16)
    direction: Literal["entry", "exit"]


@router.get("/parking/")
def get_parking():
    currently_parked = parking_system.database.get_currently_parked()

    return {
        "currently_parked": currently_parked,
        **parking_system.parking.get_statistics(currently_parked)
    }


@router.get("/parking/stats")
def get_parking_stats():
    return parking_system.parking.get_statistics(
        parking_system.database.get_currently_parked()
    )


@router.post("/parking/capacity")
def set_parking_capacity(request: CapacityRequest):
    try:
        parking_system.set_capacity(request.capacity)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "message": "Parking capacity updated",
        "total_slots": parking_system.parking.capacity
    }


@router.post("/parking/manual")
def manual_gate_event(request: ManualEventRequest):
    """Operator override for a missed or misread plate."""
    try:
        event = parking_system.handle_plate(
            request.plate_number,
            request.direction,
            source="manual",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if event is None:
        raise HTTPException(
            status_code=409,
            detail="Same plate was just recorded at this gate; wait a few seconds."
        )
    return event


PROBLEM_STATUSES = ["entry_rejected", "capacity_full", "unmatched_exit"]
CSV_COLUMNS = ["timestamp", "gate", "plate_number", "status", "slot_id",
               "security_status", "source", "confidence"]


def event_filters(gate, status, plate, since, until):
    try:
        since = date.fromisoformat(since).isoformat() if since else None
        until = (date.fromisoformat(until) + timedelta(days=1)).isoformat() if until else None
    except ValueError as exc:
        raise HTTPException(422, "Dates must look like 2026-10-18.") from exc

    return {
        "gate": gate,
        "status": PROBLEM_STATUSES if status == "problems" else status,
        "plate": normalize_plate(plate) or None if plate else None,
        "since": since,
        "until": until,
    }


@router.get("/events", tags=["Events"])
def get_events(
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    gate: Optional[Literal["entry", "exit"]] = None,
    status: Optional[str] = Query(default=None, description="An event status, or 'problems'"),
    plate: Optional[str] = Query(default=None, description="Part of a number plate"),
    since: Optional[str] = Query(default=None, description="From this day, YYYY-MM-DD"),
    until: Optional[str] = Query(default=None, description="Up to and including this day"),
):
    filters = event_filters(gate, status, plate, since, until)
    database = parking_system.database
    return {
        "events": database.get_events(limit, offset=offset, **filters),
        "total": database.count_events(**filters),
    }


@router.get("/events.csv", tags=["Events"])
def export_events(
    gate: Optional[Literal["entry", "exit"]] = None,
    status: Optional[str] = None,
    plate: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
):
    filters = event_filters(gate, status, plate, since, until)
    events = parking_system.database.get_events(100000, **filters)

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(events)

    filename = f"parking-events-{date.today().isoformat()}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
