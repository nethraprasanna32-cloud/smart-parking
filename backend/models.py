from datetime import datetime


class Vehicle:
    def __init__(
        self,
        plate_number,
        owner_name="",
        vehicle_type="",
        authorized=True,
        stolen=False
    ):
        self.plate_number = plate_number
        self.owner_name = owner_name
        self.vehicle_type = vehicle_type
        self.authorized = authorized
        self.stolen = stolen
        self.created_at = datetime.now()

    def to_dict(self):
        return {
            "plate_number": self.plate_number,
            "owner_name": self.owner_name,
            "vehicle_type": self.vehicle_type,
            "authorized": self.authorized,
            "stolen": self.stolen,
            "created_at": self.created_at.isoformat()
        }