from fastapi import APIRouter, HTTPException

from ai_pipeline.detect_and_ocr import DETECTORS
from backend.app.services.prediction_manager import MODELS
from backend.app.state import parking_system


router = APIRouter(
    prefix="/models",
    tags=["AI Models"]
)


def model_error(exc):
    if isinstance(exc, ValueError):
        return HTTPException(400, str(exc))
    if isinstance(exc, ImportError):
        return HTTPException(503, f"Missing dependency: {exc.name or exc}")
    return HTTPException(503, str(exc))


@router.get("/")
def get_models():
    return {
        "vehicle_detection": parking_system.get_detection_model(),
        "parking_prediction": parking_system.get_prediction_model(),
        "available": {
            "vehicle_detection": list(DETECTORS),
            "parking_prediction": list(MODELS),
        },
    }


@router.post("/vehicle/{model_type}")
def change_vehicle_model(model_type: str):
    try:
        parking_system.change_detection_model(model_type)
    except (ValueError, ImportError, FileNotFoundError, OSError) as exc:
        raise model_error(exc) from exc

    return {
        "message": "Vehicle detection model changed",
        "model": parking_system.get_detection_model()
    }


@router.post("/prediction/{model_type}")
def change_prediction_model(model_type: str):
    try:
        parking_system.change_prediction_model(model_type)
    except (ValueError, ImportError, FileNotFoundError, OSError) as exc:
        raise model_error(exc) from exc

    return {
        "message": "Prediction model changed",
        "model": parking_system.get_prediction_model()
    }
