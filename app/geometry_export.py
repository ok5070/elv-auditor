"""Build a backward-compatible geometry export for Room Plan Editor."""

from __future__ import annotations

from typing import Any

import ezdxf
from shapely.geometry import LineString

from app.geometry_parser import GeometryParser
from app.services.wall_consolidator import ConsolidationParams, WallConsolidator


ARCHITECTURE_TOKENS = (
    "WALL", "СТЕН", "ПЕРЕГОРОД", "A-", "АР_", "АРХИТЕКТ", "ПЛАН",
)
PARTITION_TOKENS = ("PARTITION", "ПЕРЕГОРОД", "P-WALL")
GENERIC_PLAN_LAYERS = {"PLAN", "ПЛАН"}
GENERIC_PLAN_MIN_LINEWEIGHT = 25


def _layer_matches(layer: str, tokens: tuple[str, ...]) -> bool:
    value = layer.upper()
    return any(token in value for token in tokens)


def _effective_lineweight(document: ezdxf.document.Drawing, entity: Any) -> int:
    lineweight = int(entity.dxf.get("lineweight", -1))
    if lineweight >= 0:
        return lineweight
    try:
        return int(document.layers.get(str(entity.dxf.get("layer", "0"))).dxf.get("lineweight", -1))
    except Exception:
        return -1


def _wall_items(document: ezdxf.document.Drawing) -> tuple[list[dict[str, Any]], list[LineString]]:
    walls: list[dict[str, Any]] = []
    segments: list[LineString] = []
    for entity_index, entity in enumerate(document.modelspace(), 1):
        layer = str(entity.dxf.get("layer", "0"))
        generic_plan_layer = layer.upper() in GENERIC_PLAN_LAYERS
        if not generic_plan_layer and not _layer_matches(layer, ARCHITECTURE_TOKENS):
            continue
        lineweight = _effective_lineweight(document, entity)
        if generic_plan_layer and lineweight < GENERIC_PLAN_MIN_LINEWEIGHT:
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
            wall_type = "partition" if _layer_matches(layer, PARTITION_TOKENS) else "wall"
            walls.append({
                "id": f"W-{entity_index:04d}-{segment_index:02d}",
                "type": wall_type,
                "x1": round(start[0], 3),
                "y1": round(start[1], 3),
                "x2": round(end[0], 3),
                "y2": round(end[1], 3),
                "thickness": 7.0 if wall_type == "partition" else 13.0,
                "layer": layer,
                "source": "dxf",
                "confidence": "generic_plan_lineweight" if generic_plan_layer else "explicit_architecture_layer",
            })
    return walls, segments


def _consolidate_wall_items(
    wall_items: list[dict[str, Any]],
    k: float,
) -> tuple[list[dict[str, Any]], dict[str, int | float]]:
    buckets: dict[tuple[str, float, str, str], list[tuple[tuple[float, float], tuple[float, float]]]] = {}
    for wall in wall_items:
        key = (
            str(wall["type"]),
            float(wall["thickness"]),
            str(wall["layer"]),
            str(wall["confidence"]),
        )
        buckets.setdefault(key, []).append(
            ((float(wall["x1"]), float(wall["y1"])), (float(wall["x2"]), float(wall["y2"])))
        )

    result_items: list[dict[str, Any]] = []
    protected_openings = 0
    merge_operations = 0
    for (wall_type, thickness, layer, confidence), segments in buckets.items():
        result = WallConsolidator(ConsolidationParams(k=k)).run_dry_run(segments)
        protected_openings += result.metrics.protected_openings_count
        merge_operations += result.metrics.merge_operations_count
        for point_a, point_b in result.consolidated_segments_cad:
            result_items.append({
                "id": f"W-{len(result_items) + 1:04d}",
                "type": wall_type,
                "x1": round(point_a[0], 3),
                "y1": round(point_a[1], 3),
                "x2": round(point_b[0], 3),
                "y2": round(point_b[1], 3),
                "thickness": thickness,
                "layer": layer,
                "source": "dxf_consolidated",
                "confidence": confidence,
            })

    return result_items, {
        "raw_candidates": len(wall_items),
        "final_candidates": len(result_items),
        "merge_operations": merge_operations,
        "protected_openings": protected_openings,
    }


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


def build_geometry_export(
    document: ezdxf.document.Drawing,
    source: str,
    project_name: str = "Проект",
    k: float | None = None,
) -> dict[str, Any]:
    raw_walls, segments = _wall_items(document)
    walls = raw_walls
    wall_detection: dict[str, Any] = {
        "mode": "explicit_layers_or_generic_plan_lineweight",
        "generic_plan_min_lineweight": GENERIC_PLAN_MIN_LINEWEIGHT,
        "raw_candidates": len(raw_walls),
        "final_candidates": len(raw_walls),
        "consolidated": False,
    }
    if k is not None and k > 0:
        walls, metrics = _consolidate_wall_items(raw_walls, k)
        wall_detection.update(metrics)
        wall_detection["consolidated"] = True
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
            "k": k,
            "coordinate_system": "source_cad",
            "origin": {"x": round(min_x, 3), "y": round(min_y, 3)},
            "manual_review_required": True,
            "rooms_detection": "disabled_generic_plan_layer" if generic_plan_layer else "polygonize",
            "wall_detection": wall_detection,
        },
    }


def adapt_room_plan_geometry(
    editor_payload: dict[str, Any],
    params: ConsolidationParams | None = None,
) -> dict[str, Any]:
    """Adapt Room Plan Editor walls to the existing geometry.v2 contract.

    The input payload is only read.  Wall consolidation is run independently
    for each existing ``(type, thickness)`` group so walls and partitions are
    never merged with one another.
    """
    consolidation_params = params or ConsolidationParams()
    raw_walls = editor_payload.get("walls", [])
    buckets: dict[tuple[str, float], list[tuple[tuple[float, float], tuple[float, float]]]] = {}

    for wall in raw_walls:
        wall_type = str(wall.get("type", "wall"))
        thickness = float(wall.get("thickness", 0.0))
        segment = (
            (float(wall["x1"]), float(wall["y1"])),
            (float(wall["x2"]), float(wall["y2"])),
        )
        buckets.setdefault((wall_type, thickness), []).append(segment)

    consolidated_walls: list[dict[str, Any]] = []
    wall_counter = 1
    for (wall_type, thickness), segments in buckets.items():
        result = WallConsolidator(consolidation_params).run_dry_run(segments)
        for (p1, p2) in result.consolidated_segments_cad:
            consolidated_walls.append({
                "id": f"W-{wall_counter:04d}",
                "type": wall_type,
                "x1": round(p1[0], 3),
                "y1": round(p1[1], 3),
                "x2": round(p2[0], 3),
                "y2": round(p2[1], 3),
                "thickness": thickness,
                "source": "room-plan-editor",
            })
            wall_counter += 1

    canvas = editor_payload.get("canvas", {})
    return {
        "version": 2,
        "schema_version": "2.0",
        "canvas": {
            "width": float(canvas.get("width", 0.0)),
            "height": float(canvas.get("height", 0.0)),
        },
        "walls": consolidated_walls,
        "doors": [dict(door) for door in editor_payload.get("doors", [])],
        "windows": [dict(window) for window in editor_payload.get("windows", [])],
        "rooms": [],
        "devices": [],
        "cable_routes": [],
        "metadata": {
            "source": "room-plan-editor",
            "coordinate_system": "editor_canvas",
            "manual_review_required": True,
            "consolidated": True,
        },
    }
