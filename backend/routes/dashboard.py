from fastapi import APIRouter

from backend.app_state import parking_system


router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"]
)


@router.get("/summary")
def dashboard_summary():

    parking_status = (
        parking_system.database
        .get_parking_status()
    )

    total_slots = len(parking_status)

    occupied = sum(
        1
        for slot in parking_status
        if slot.get("occupied", False)
    )

    available = total_slots - occupied

    occupancy_rate = (
        (occupied / total_slots) * 100
        if total_slots > 0
        else 0
    )

    vehicles = (
        parking_system.database
        .get_all_vehicles()
    )

    stolen_count = sum(
        1
        for vehicle in vehicles
        if vehicle.get("stolen", False)
    )

    unauthorized_count = sum(
        1
        for vehicle in vehicles
        if not vehicle.get("authorized", False)
    )

    return {
        "parking": {
            "total_slots": total_slots,
            "occupied": occupied,
            "available": available,
            "occupancy_rate": round(
                occupancy_rate,
                2
            )
        },

        "vehicles": {
            "total": len(vehicles)
        },

        "security": {
            "stolen_detected": stolen_count,
            "unauthorized": unauthorized_count
        },

        "prediction": {
            "model": (
                parking_system
                .get_prediction_model()
            ),
            "predicted_occupancy": 0
        }
    }

@router.post("/prediction")
def predict_parking(
    recent_occupancy: list
):

    prediction = (
        parking_system.predict_occupancy(
            recent_occupancy
        )
    )

    return {
        "model": (
            parking_system
            .get_prediction_model()
        ),
        "predicted_occupancy": prediction
    }