from datetime import datetime

from backend.database import Database


class DatabaseService:

    def __init__(self):
        self.database = Database()
        self.connected = False

    def connect(self):
        self.database.connect()
        self.connected = True

    def save_vehicle(self, vehicle):
        if not self.connected:
            return

        self.database.add_vehicle(vehicle)

    def get_vehicle(self, plate_number):
        if not self.connected:
            return None

        return self.database.get_vehicle(
            plate_number
        )

    def save_parking_results(self, parking_results):
        if not self.connected:
            return

        for result in parking_results:

            data = {
                "slot_id": result["slot_id"],
                "occupied": result["occupied"],
                "status": result["status"],
                "timestamp": datetime.now().isoformat()
            }

            self.database.save_parking_status(
                data
            )

    def save_detection(self, detection):
        if not self.connected:
            return

        data = {
            **detection,
            "timestamp": datetime.now().isoformat()
        }

        self.database.save_detection(data)

    def get_all_vehicles(self):
        if not self.connected:
            return []

        return self.database.get_all_vehicles()

    def get_parking_status(self):
        if not self.connected:
            return []

        return self.database.get_parking_status()