from fastapi import APIRouter

from backend.app_state import parking_system


router = APIRouter(
    prefix="/parking",
    tags=["Parking"]
)


@router.get("/")
def get_parking():

    results = (
        parking_system.parking
        .get_statistics(
            parking_system.parking
            .check_slot_occupancy([])
        )
    )

    return results


@router.get("/stats")
def get_parking_stats():

    results = (
        parking_system.parking
        .get_statistics(
            parking_system.parking
            .check_slot_occupancy([])
        )
    )

    return results


@router.post("/slots")
def set_parking_slots(slots: list):

    parking_system.set_parking_slots(
        slots
    )

    return {
        "message": "Parking slots updated",
        "total_slots": len(slots)
    }