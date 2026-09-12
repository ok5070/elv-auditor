from pydantic import BaseModel, Field
from typing import List, Literal, Dict, Union

class Point3D(BaseModel):
    x: float
    y: float
    z: float

class Point2D(BaseModel):
    x: float
    y: float

class DoorInput(BaseModel):
    door_id: str
    width_mm: int = Field(..., ge=500, le=3000)
    is_fire_exit: bool = False
    from_zone: str
    to_zone: str
    two_way_security: bool = False

class CameraInput(BaseModel):
    camera_id: str
    model: str = "IP 2MP 2.8mm"
    sensor_w_mm: float = 5.12
    resolution_w: int = 1920
    focal_length_mm: float = 2.8
    pos: Point3D
    dist_to_wall: float = Field(..., ge=0.1)

class WifiAPInput(BaseModel):
    ap_id: str
    model: str = "Ceiling AP Wi-Fi 6"
    tx_power_dbm: float = 20.0
    pos: Point2D
    frequency_ghz: float = 5.0
    target_zone_name: str
    target_zone_clients: int
    wall_material: Literal["drywall", "brick", "concrete"] = "drywall"
    walls_crossed: int = 0
    test_distance_m: float = Field(..., ge=0.5)

class AudioZoneInput(BaseModel):
    zone_id: str
    name: str
    area_sqm: float = Field(..., gt=0)
    ceiling_height_m: float = Field(..., ge=2.0)
    system_type: Literal["100V", "LOW_Z_8OHM", "LOW_Z_16OHM"]
    target_sound_pressure_db: int = Field(75, ge=60, le=100)
    cable_distance_to_rack_m: float = Field(..., ge=0)

class AuditRequest(BaseModel):
    project_name: str
    client_name: str
    rack_pos: Point3D
    ceiling_tray_height: float = Field(3.0, ge=2.0)
    doors: List[DoorInput] = []
    cameras: List[CameraInput] = []
    wifi_points: List[WifiAPInput] = []
    audio_zones: List[AudioZoneInput] = []

class Issue(BaseModel):
    subsystem: str
    severity: Literal["CRITICAL", "WARNING"]
    element: str
    msg: str

class AuditResponse(BaseModel):
    project: str
    client: str
    verdict: Literal["APPROVED", "WARNING", "REJECTED"]
    cable_total_m: float
    issues: List[Issue]
    bom: Dict[str, Union[int, float]]
