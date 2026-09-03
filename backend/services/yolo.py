from ai.vehicle_detection.yolo11 import YOLO11VehicleDetector


class YOLOService:

    def __init__(self):
        self.detector = YOLO11VehicleDetector()

    def detect_vehicles(self, frame):
        """
        Detect vehicles in a camera frame.
        """

        return self.detector.detect(frame)