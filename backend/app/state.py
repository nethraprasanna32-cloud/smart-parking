from backend.app.services.auth import Auth
from backend.app.services.gate_camera import GateCamera
from backend.app.services.parking_system import SmartParkingSystem


parking_system = SmartParkingSystem()

cameras = {
    gate: GateCamera(gate, parking_system)
    for gate in ("entry", "exit")
}

auth = Auth()
