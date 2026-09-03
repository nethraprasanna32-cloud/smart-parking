from pymongo import MongoClient
import os


class Database:

    def __init__(self):
        self.client = None
        self.db = None
        self.vehicles = None
        self.parking = None
        self.detections = None

    def connect(self):
        """
        Connect to MongoDB.
        """

        mongo_url = os.getenv(
            "MONGO_URL",
            "mongodb://localhost:27017"
        )

        self.client = MongoClient(mongo_url)

        self.db = self.client["smart_parking"]

        self.vehicles = self.db["vehicles"]
        self.parking = self.db["parking"]
        self.detections = self.db["detections"]

    def add_vehicle(self, vehicle):
        """
        Add a vehicle to the database.
        """

        self.vehicles.update_one(
            {
                "plate_number":
                    vehicle["plate_number"]
            },
            {
                "$set": vehicle
            },
            upsert=True
        )

    def get_vehicle(self, plate_number):
        """
        Find a vehicle by license plate.
        """

        return self.vehicles.find_one(
            {
                "plate_number": plate_number
            },
            {
                "_id": 0
            }
        )

    def save_parking_status(self, data):
        """
        Save current parking information.
        """

        self.parking.update_one(
            {
                "slot_id": data["slot_id"]
            },
            {
                "$set": data
            },
            upsert=True
        )

    def save_detection(self, data):
        """
        Store a vehicle/plate detection event.
        """

        self.detections.insert_one(data)

    def get_all_vehicles(self):
        """
        Return all registered vehicles.
        """

        return list(
            self.vehicles.find(
                {},
                {
                    "_id": 0
                }
            )
        )

    def get_parking_status(self):
        """
        Return the current status of all
        parking slots.
        """

        return list(
            self.parking.find(
                {},
                {
                    "_id": 0
                }
            )
        )