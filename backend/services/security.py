class SecurityService:

    def __init__(self):
        self.registered_vehicles = {}

    def register_vehicle(
        self,
        plate_number,
        owner_name="",
        vehicle_type=""
    ):
        self.registered_vehicles[plate_number] = {
            "plate_number": plate_number,
            "owner_name": owner_name,
            "vehicle_type": vehicle_type,
            "authorized": True,
            "stolen": False
        }

    def mark_stolen(self, plate_number):

        if plate_number in self.registered_vehicles:
            self.registered_vehicles[
                plate_number
            ]["stolen"] = True

    def check_vehicle(self, plate_number):

        vehicle = self.registered_vehicles.get(
            plate_number
        )

        if vehicle is None:
            return {
                "plate_number": plate_number,
                "status": "UNKNOWN",
                "authorized": False,
                "stolen": False,
                "access_granted": False
            }

        if vehicle["stolen"]:
            return {
                "plate_number": plate_number,
                "status": "STOLEN",
                "authorized": False,
                "stolen": True,
                "access_granted": False
            }

        if vehicle["authorized"]:
            return {
                "plate_number": plate_number,
                "status": "AUTHORIZED",
                "authorized": True,
                "stolen": False,
                "access_granted": True
            }

        return {
            "plate_number": plate_number,
            "status": "UNAUTHORIZED",
            "authorized": False,
            "stolen": False,
            "access_granted": False
        }