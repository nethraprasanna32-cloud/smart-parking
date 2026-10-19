class SecurityService:
    """Access decisions, read straight from the vehicle registry."""

    def __init__(self, database):
        self.database = database

    def check_vehicle(self, plate_number):
        vehicle = self.database.get_vehicle(plate_number)

        if vehicle is None:
            status = "UNKNOWN"
        elif vehicle.get("stolen"):
            status = "STOLEN"
        elif vehicle.get("authorized"):
            status = "AUTHORIZED"
        else:
            status = "UNAUTHORIZED"

        return {
            "plate_number": plate_number,
            "status": status,
            "authorized": status == "AUTHORIZED",
            "stolen": status == "STOLEN",
            "access_granted": status == "AUTHORIZED",
        }
