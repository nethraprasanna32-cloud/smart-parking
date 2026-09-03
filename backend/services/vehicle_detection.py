from ai.vehicle_detection.detector import VehicleDetectionManager


class VehicleDetectionService:

    def __init__(self, model_type="yolo11"):
        self.detector = VehicleDetectionManager(
            model_type=model_type
        )

    def detect_vehicles(self, frame):
        return self.detector.detect(frame)

    def change_model(self, model_type):
        self.detector.change_model(model_type)

    def get_current_model(self):
        return self.detector.model_type