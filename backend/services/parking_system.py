from backend.services.prediction_manager import (
    PredictionManager
)
from datetime import datetime

from backend.services.vehicle_detection import (
    VehicleDetectionService
)
from backend.services.parking import (
    ParkingSlotManager
)
from backend.services.security import (
    SecurityService
)
from backend.services.alpr_service import (
    ALPRManager
)
from backend.services.database_service import (
    DatabaseService
)


class SmartParkingSystem:

    def __init__(self):

        self.vehicle_detector = (
            VehicleDetectionService(
                model_type="yolo11"
            )
        )

        self.parking = ParkingSlotManager()

        self.security = SecurityService()

        self.alpr = ALPRManager()

        self.database = DatabaseService()

        self.prediction = PredictionManager(
            model_type="lstm",
            sequence_length=10
        )

    def connect_database(self):
        self.database.connect()

    def set_parking_slots(self, slots):
        self.parking.set_slots(slots)

    def change_detection_model(self, model_type):
        self.vehicle_detector.change_model(
            model_type
        )

    def get_detection_model(self):
        return self.vehicle_detector.get_current_model()

    def process_frame(self, frame):

        # 1. Detect vehicles
        vehicles = (
            self.vehicle_detector.detect_vehicles(
                frame
            )
        )

        # 2. Check parking occupancy
        parking_results = (
            self.parking.check_slot_occupancy(
                vehicles
            )
        )

        # 3. Calculate statistics
        statistics = (
            self.parking.get_statistics(
                parking_results
            )
        )

        # 4. Detect license plates
        plates = self.alpr.recognize_plates(
            frame
        )

        # 5. Check security
        security_results = []

        for plate in plates:

            plate_number = plate["plate_text"]

            if plate_number:

                security_status = (
                    self.security.check_vehicle(
                        plate_number
                    )
                )

                security_results.append(
                    security_status
                )

        # 6. Save parking information
        self.database.save_parking_results(
            parking_results
        )

        # 7. Save vehicle detections
        for vehicle in vehicles:

            self.database.save_detection(
                vehicle
            )

        # 8. Save license plate detections
        for plate in plates:

            self.database.save_detection(
                plate
            )

        return {

            "timestamp":
                datetime.now().isoformat(),

            "model":
                self.vehicle_detector
                .get_current_model(),

            "vehicles":
                vehicles,

            "parking":
                parking_results,

            "statistics":
                statistics,

            "plates":
                plates,

            "security":
                security_results
        }
    
    def train_prediction_model(
        self,
        occupancy_data,
        epochs=20
    ):

        self.prediction.train(
            occupancy_data,
            epochs=epochs
        )

    def predict_occupancy(
        self,
        recent_occupancy
    ):

        return self.prediction.predict(
            recent_occupancy
        )

    def change_prediction_model(
        self,
        model_type
    ):

        self.prediction.change_model(
            model_type
        )

    def get_prediction_model(self):

        return self.prediction.get_current_model()
        
    def check_vehicle(self, plate_number):

        return self.security.check_vehicle(
            plate_number
        )