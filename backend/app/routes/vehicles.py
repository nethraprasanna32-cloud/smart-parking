from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ai_pipeline.detect_and_ocr import is_valid_plate, normalize_plate
from backend.app.state import parking_system


router = APIRouter(
    prefix="/vehicles",
    tags=["Vehicles"]
)


class VehicleRequest(BaseModel):
    plate_number: str = Field(min_length=1, max_length=16)
    owner_name: str = Field(default="", max_length=80)
    vehicle_type: str = Field(default="car", max_length=20)
    authorized: bool = True


class VehicleFlags(BaseModel):
    authorized: Optional[bool] = None
    stolen: Optional[bool] = None


def plate_or_400(plate_number):
    plate_number = normalize_plate(plate_number)
    if not plate_number:
        raise HTTPException(400, "Plate number must contain letters or digits.")
    return plate_number


@router.get("/")
def get_vehicles():
    vehicles = parking_system.database.get_all_vehicles()
    parked = {
        vehicle["plate_number"]
        for vehicle in parking_system.database.get_currently_parked()
    }
    for vehicle in vehicles:
        vehicle["inside"] = vehicle["plate_number"] in parked
    vehicles.sort(key=lambda vehicle: vehicle["plate_number"])

    return {"vehicles": vehicles}


@router.get("/{plate_number}")
def get_vehicle(plate_number: str):
    plate_number = plate_or_400(plate_number)
    vehicle = parking_system.database.get_vehicle(plate_number) or {
        "plate_number": plate_number
    }

    return {
        **vehicle,
        **parking_system.check_vehicle(plate_number),
    }


@router.post("/register", status_code=201)
def register_vehicle(request: VehicleRequest):
    plate_number = plate_or_400(request.plate_number)

    vehicle = {
        **request.model_dump(),
        "plate_number": plate_number,
        "stolen": False,
    }
    parking_system.database.save_vehicle(vehicle)
    parking_system.bump()

    return {
        "message": "Vehicle registered",
        "valid_format": is_valid_plate(plate_number),
        **vehicle,
    }


@router.post("/{plate_number}/flag")
def flag_vehicle(plate_number: str, flags: VehicleFlags):
    plate_number = plate_or_400(plate_number)
    fields = flags.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(400, "Provide authorized and/or stolen.")

    vehicle = parking_system.database.update_vehicle(plate_number, fields)
    if vehicle is None:
        raise HTTPException(404, f"{plate_number} is not registered.")
    parking_system.bump()

    return vehicle


@router.delete("/{plate_number}")
def delete_vehicle(plate_number: str):
    plate_number = plate_or_400(plate_number)
    if not parking_system.database.delete_vehicle(plate_number):
        raise HTTPException(404, f"{plate_number} is not registered.")
    parking_system.bump()

    return {"message": "Vehicle removed", "plate_number": plate_number}
