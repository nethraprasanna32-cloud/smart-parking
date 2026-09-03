from backend.services.parking_system import SmartParkingSystem


class ProcessingService:

    def __init__(self):
        self.system = SmartParkingSystem()

    def process_frame(self, frame):
        return self.system.process_frame(frame)

    def set_parking_slots(self, slots):
        self.system.set_parking_slots(slots)

    def change_detection_model(self, model_type):
        self.system.change_detection_model(
            model_type
        )

    def change_prediction_model(self, model_type):
        self.system.change_prediction_model(
            model_type
        )

    def get_detection_model(self):
        return self.system.get_detection_model()

    def get_prediction_model(self):
        return self.system.get_prediction_model()

    def predict_occupancy(self, data):
        return self.system.predict_occupancy(data)

    def register_vehicle(
        self,
        plate_number,
        owner_name="",
        vehicle_type=""
    ):
        self.system.security.register_vehicle(
            plate_number,
            owner_name,
            vehicle_type
        )

        vehicle = {
            "plate_number": plate_number,
            "owner_name": owner_name,
            "vehicle_type": vehicle_type,
            "authorized": True,
            "stolen": False
        }

        self.system.database.save_vehicle(
            vehicle
        )

        return vehicle