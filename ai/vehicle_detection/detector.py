from ai.vehicle_detection.yolo11 import YOLO11VehicleDetector
from ai.vehicle_detection.rtdetr import RTDETRVehicleDetector
from ai.vehicle_detection.vit import VisionTransformerVehicleDetector
from ai.vehicle_detection.efficientdet import EfficientDetVehicleDetector


class VehicleDetectionManager:

    def __init__(self, model_type="yolo11"):

        self.model_type = model_type

        if model_type == "yolo11":
            self.detector = YOLO11VehicleDetector()

        elif model_type == "rtdetr":
            self.detector = RTDETRVehicleDetector()

        elif model_type == "vit":
            self.detector = VisionTransformerVehicleDetector()

        elif model_type == "efficientdet":
            self.detector = EfficientDetVehicleDetector()

        else:
            raise ValueError(
                "Unsupported model type. "
                "Choose yolo11, rtdetr, vit, or efficientdet."
            )

    def detect(self, frame):
        return self.detector.detect(frame)

    def change_model(self, model_type):

        self.model_type = model_type

        if model_type == "yolo11":
            self.detector = YOLO11VehicleDetector()

        elif model_type == "rtdetr":
            self.detector = RTDETRVehicleDetector()

        elif model_type == "vit":
            self.detector = VisionTransformerVehicleDetector()

        elif model_type == "efficientdet":
            self.detector = EfficientDetVehicleDetector()

        else:
            raise ValueError(
                "Unsupported model type. "
                "Choose yolo11, rtdetr, vit, or efficientdet."
            )