from fastapi import APIRouter

from backend.app_state import parking_system


router = APIRouter(
    prefix="/vehicles",
    tags=["Vehicles"]
)


@router.get("/")
def get_vehicles():

    vehicles = (
        parking_system.database
        .get_all_vehicles()
    )

    return {
        "vehicles": vehicles
    }


@router.get("/{plate_number}")
def get_vehicle(plate_number: str):

    vehicle = (
        parking_system.database
        .get_vehicle(plate_number)
    )

    if vehicle is None:

        return {
            "plate_number": plate_number,
            "status": "UNKNOWN"
        }

    security_status = (
        parking_system.check_vehicle(
            plate_number
        )
    )

    return {
        **vehicle,
        **security_status
    }


@router.post("/register")
def register_vehicle(
    plate_number: str,
    owner_name: str = "",
    vehicle_type: str = ""
):

    parking_system.security.register_vehicle(
        plate_number=plate_number,
        owner_name=owner_name,
        vehicle_type=vehicle_type
    )

    vehicle = {
        "plate_number": plate_number,
        "owner_name": owner_name,
        "vehicle_type": vehicle_type,
        "authorized": True,
        "stolen": False
    }

    parking_system.database.save_vehicle(
        vehicle
    )

    return {
        "message": "Vehicle registered",
        **vehicle
    }