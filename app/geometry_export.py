"""Build a backward-compatible geometry export for Room Plan Editor."""

from __future__ import annotations

from typing import Any

import ezdxf
from shapely.geometry import LineString

from app.geometry_parser import GeometryParser


ARCHITECTURE_TOKENS = (
    "WALL", "СТЕН", "ПЕРЕГОРОД", "A-", "АР_", "АРХИТЕКТ", "ПЛАН",
)


def _layer_matches(layer: str, tokens: tuple[str, ...]) -> bool:
    value = layer.upper()
    return any(token in value for token in tokens)


def _wall_items(document: ezdxf.document.Drawing) -> tuple[list[dict[str, Any]], list[LineString]]:
    walls: list[dict[str, Any]] = []
    segments: list[LineString] = []
    for entity_index, entity in enumerate(document.modelspace(), 1):
        layer = str(entity.dxf.get("layer", "0"))
        if not _layer_matches(layer, ARCHITECTURE_TOKENS):
            continue
        points: list[tuple[float, float]] = []
        if entity.dxftype() == "LINE":
            points = [
                (float(entity.dxf.start.x), float(entity.dxf.start.y)),
                (float(entity.dxf.end.x), float(entity.dxf.end.y)),
            ]
        elif entity.dxftype() == "LWPOLYLINE":
            raw_points = list(entity.get_points("xy"))
            points = [(float(point[0]), float(point[1])) for point in raw_points]
            if entity.closed and len(points) > 2:
                points.append(points[0])
        if len(points) < 2:
            continue
        for segment_index, (start, end) in enumerate(zip(points, points[1:]), 1):
            if start == end:
                continue
            segments.append(LineString([start, end]))
            walls.append({
                "id": f"W-{entity_index:04d}-{segment_index:02d}",
                "type": "wall",
                "x1": round(start[0], 3),
                "y1": round(start[1], 3),
                "x2": round(end[0], 3),
                "y2": round(end[1], 3),
                "thickness": 13.0,
                "layer": layer,
                "source": "dxf",
            })
    return walls, segments


def _block_text_point(document: ezdxf.document.Drawing, block_name: str) -> tuple[float, float] | None:
    """Read the embedded label position used by some exported CAD blocks.

    A few source drawings contain INSERTs at (0, 0), while the block's MTEXT
    entities retain their real drawing coordinates.  This is intentionally
    narrow: text-bearing blocks only are treated this way.
    """
    try:
        block = document.blocks.get(block_name)
    except Exception:
        return None
    points = []
    for entity in block:
        if entity.dxftype() not in {"TEXT", "MTEXT"}:
            continue
        point = entity.dxf.get("insert")
        if point is not None:
            points.append((float(point.x), float(point.y)))
    if not points:
        return None
    return (
        sum(point[0] for point in points) / len(points),
        sum(point[1] for point in points) / len(points),
    )


def _devices(document: ezdxf.document.Drawing) -> list[dict[str, Any]]:
    devices: list[dict[str, Any]] = []
    keywords = {
        "cctv": ("CAM", "CCTV", "СОТ", "КАМЕР"),
        "skud": ("СКУД", "DOOR", "ДВЕР", "READER", "СЧИТ", "ЗАМОК"),
        "network": ("WIFI", "WI-FI", "СКС", "RJ45", "РОЗЕТ"),
        "rack": ("RACK", "ШКАФ", "СТОЙК", "ТК"),
    }
    counters: dict[str, int] = {}
    for entity in document.modelspace():
        if entity.dxftype() not in {"INSERT", "POINT", "CIRCLE"}:
            continue
        layer = str(entity.dxf.get("layer", "0"))
        block = str(entity.dxf.get("name", "")) if entity.dxftype() == "INSERT" else ""
        haystack = f"{layer} {block}".upper()
        if "ОБОРУДОВАН" in layer:
            haystack += " CCTV"
        system = next((name for name, words in keywords.items() if any(word in haystack for word in words)), None)
        if system is None:
            continue
        if entity.dxftype() == "INSERT":
            point = entity.dxf.get("insert")
        elif entity.dxftype() == "POINT":
            point = entity.dxf.get("location")
        else:
            point = entity.dxf.get("center")
        if entity.dxftype() == "INSERT" and point is not None:
            if float(point.x) == 0.0 and float(point.y) == 0.0:
                embedded_point = _block_text_point(document, block)
                if embedded_point is None:
                    continue
                point = embedded_point
        if point is None:
            continue
        counters[system] = counters.get(system, 0) + 1
        devices.append({
            "id": f"{system.upper()}-{counters[system]:03d}",
            "system": system,
            "type": block or entity.dxftype().lower(),
            "x": round(float(point[0] if isinstance(point, tuple) else point.x), 3),
            "y": round(float(point[1] if isinstance(point, tuple) else point.y), 3),
            "z": round(float(getattr(point, "z", 0.0)), 3),
            "rotation": round(float(entity.dxf.get("rotation", 0.0)) if entity.dxftype() == "INSERT" else 0.0, 3),
            "layer": layer,
            "block": block or entity.dxftype(),
            "source": "dxf",
            "confidence": "layer_or_block_match",
        })
    return devices


def build_geometry_export(document: ezdxf.document.Drawing, source: str, project_name: str = "Проект") -> dict[str, Any]:
    walls, segments = _wall_items(document)
    rooms = []
    generic_plan_layer = any(item["layer"].upper() == "ПЛАН" for item in walls)
    if not generic_plan_layer:
        for index, room in enumerate(GeometryParser.detect_rooms(segments), 1):
            polygon = room["polygon"]
            rooms.append({
                "id": f"ROOM-{index:03d}",
                "name": f"Помещение {index}",
                "polygon": [[round(float(x), 3), round(float(y), 3)] for x, y in polygon.exterior.coords],
                "area_m2": room["area_sqm"],
                "perimeter_m": room["perimeter_m"],
                "source": "dxf_polygonize",
            })
    devices = _devices(document)
    coordinates = [(item["x1"], item["y1"]) for item in walls] + [(item["x2"], item["y2"]) for item in walls]
    coordinates += [(item["x"], item["y"]) for item in devices]
    if coordinates:
        min_x = min(point[0] for point in coordinates)
        min_y = min(point[1] for point in coordinates)
        max_x = max(point[0] for point in coordinates)
        max_y = max(point[1] for point in coordinates)
    else:
        min_x = min_y = 0.0
        max_x = max_y = 1.0
    return {
        "version": 2,
        "schema_version": "2.0",
        "canvas": {"width": round(max_x - min_x, 3), "height": round(max_y - min_y, 3)},
        "walls": walls,
        "doors": [],
        "windows": [],
        "rooms": rooms,
        "devices": devices,
        "cable_routes": [],
        "metadata": {
            "project": project_name,
            "source": source,
            "coordinate_system": "source_cad",
            "origin": {"x": round(min_x, 3), "y": round(min_y, 3)},
            "manual_review_required": True,
            "rooms_detection": "disabled_generic_plan_layer" if generic_plan_layer else "polygonize",
        },
    }
