"""
Модели данных для цифровой модели объекта.
Определяет структуру стен, дверей, оборудования и помещений.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import uuid

@dataclass
class Point:
    x: float
    y: float
    
    def to_dict(self) -> Dict[str, float]:
        return {"x": round(self.x, 3), "y": round(self.y, 3)}

@dataclass
class Wall:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    start: Point = None
    end: Point = None
    thickness: float = 0.0
    layer: str = ""
    material: str = "unknown"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "start": self.start.to_dict() if self.start else {},
            "end": self.end.to_dict() if self.end else {},
            "thickness": self.thickness,
            "layer": self.layer,
            "material": self.material,
            "type": "wall"
        }

@dataclass
class Door:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    position: Point = None
    width: float = 0.0
    height: float = 2.1
    opening_angle: float = 90.0
    wall_id: Optional[str] = None
    layer: str = ""
    type_name: str = "door"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "position": self.position.to_dict() if self.position else {},
            "width": self.width,
            "height": self.height,
            "opening_angle": self.opening_angle,
            "wall_id": self.wall_id,
            "layer": self.layer,
            "type": "door"
        }

@dataclass
class Equipment:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    type: str = "unknown" # camera, sensor, siren, etc.
    position: Point = None
    layer: str = ""
    block_name: str = ""
    attributes: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "position": self.position.to_dict() if self.position else {},
            "layer": self.layer,
            "block_name": self.block_name,
            "attributes": self.attributes,
            "category": "equipment"
        }

@dataclass
class CableRoute:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    points: List[Point] = field(default_factory=list)
    layer: str = ""
    cable_type: str = "unknown"
    length: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "points": [p.to_dict() for p in self.points],
            "layer": self.layer,
            "cable_type": self.cable_type,
            "length": round(self.length, 2),
            "category": "cable_route"
        }

@dataclass
class Room:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    area: float = 0.0
    boundary: List[Point] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "area": round(self.area, 2),
            "boundary": [p.to_dict() for p in self.boundary],
            "category": "room"
        }

@dataclass
class ProjectModel:
    """Основная модель проекта"""
    name: str = ""
    floor: str = ""
    walls: List[Wall] = field(default_factory=list)
    doors: List[Door] = field(default_factory=list)
    equipment: List[Equipment] = field(default_factory=list)
    cable_routes: List[CableRoute] = field(default_factory=list)
    rooms: List[Room] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "meta": {
                "name": self.name,
                "floor": self.floor,
                "version": "1.0",
                "source": "dxf_import"
            },
            "data": {
                "walls": [w.to_dict() for w in self.walls],
                "doors": [d.to_dict() for d in self.doors],
                "equipment": [e.to_dict() for e in self.equipment],
                "cable_routes": [c.to_dict() for c in self.cable_routes],
                "rooms": [r.to_dict() for r in self.rooms]
            }
        }
