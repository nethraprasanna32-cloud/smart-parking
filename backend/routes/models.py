from fastapi import APIRouter

from backend.app_state import parking_system


router = APIRouter(
    prefix="/models",
    tags=["AI Models"]
)


@router.get("/")
def get_models():

    return {
        "vehicle_detection": (
            parking_system
            .get_detection_model()
        ),
        "parking_prediction": (
            parking_system
            .get_prediction_model()
        )
    }


@router.post("/vehicle/{model_type}")
def change_vehicle_model(
    model_type: str
):

    parking_system.change_detection_model(
        model_type
    )

    return {
        "message": "Vehicle detection model changed",
        "model": (
            parking_system
            .get_detection_model()
        )
    }


@router.post("/prediction/{model_type}")
def change_prediction_model(
    model_type: str
):

    parking_system.change_prediction_model(
        model_type
    )

    return {
        "message": "Prediction model changed",
        "model": (
            parking_system
            .get_prediction_model()
        )
    }