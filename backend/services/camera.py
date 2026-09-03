import cv2

from backend.services.vehicle_detection import (
    VehicleDetectionService
)


class CameraService:

    def __init__(self, camera_source=0):
        self.camera_source = camera_source
        self.camera = None

        self.vehicle_detector = (
            VehicleDetectionService(
                model_type="yolo11"
            )
        )

    def start(self):
        self.camera = cv2.VideoCapture(
            self.camera_source
        )

        if not self.camera.isOpened():
            raise RuntimeError(
                "Could not open camera."
            )

    def read_frame(self):
        if self.camera is None:
            raise RuntimeError(
                "Camera has not been started."
            )

        success, frame = self.camera.read()

        if not success:
            return None, []

        detections = (
            self.vehicle_detector.detect_vehicles(
                frame
            )
        )

        return frame, detections

    def stop(self):
        if self.camera is not None:
            self.camera.release()
            self.camera = None

    def change_model(self, model_type):
        self.vehicle_detector.change_model(
            model_type
        )

    def get_current_model(self):
        return self.vehicle_detector.get_current_model()