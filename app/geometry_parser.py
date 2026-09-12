import math
import ezdxf
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import polygonize, unary_union
from typing import List, Dict, Any, Tuple

class GeometryParser:
    @staticmethod
    def extract_wall_segments(doc: ezdxf.document.Drawing, target_layers: List[str] = None) -> List[LineString]:
        """Извлекает отрезки стен со слоев архитектуры."""
        if not target_layers:
            target_layers = ['WALLS', 'WALL', 'АРХИТЕКТУРА', 'ПЕРЕГОРОДКИ', 'СТЕНЫ', '0']
        
        target_layers_upper = [l.upper() for l in target_layers]
        msp = doc.modelspace()
        segments = []

        for entity in msp:
            layer = entity.dxf.layer.upper()
            if not any(t in layer for t in target_layers_upper):
                continue

            if entity.dxftype() == 'LINE':
                start = (entity.dxf.start.x, entity.dxf.start.y)
                end = (entity.dxf.end.x, entity.dxf.end.y)
                if start != end:
                    segments.append(LineString([start, end]))

            elif entity.dxftype() == 'LWPOLYLINE':
                points = entity.get_points('xy')
                for i in range(len(points) - 1):
                    p1, p2 = points[i], points[i + 1]
                    if p1 != p2:
                        segments.append(LineString([p1, p2]))
                if entity.closed and len(points) > 2:
                    p_last, p_first = points[-1], points[0]
                    if p_last != p_first:
                        segments.append(LineString([p_last, p_first]))

        return segments

    @staticmethod
    def detect_rooms(wall_segments: List[LineString]) -> List[Dict[str, Any]]:
        """Строит полигоны помещений и рассчитывает их площадь и периметр."""
        if not wall_segments:
            return []
        
        merged_lines = unary_union(wall_segments)
        polygons = list(polygonize(merged_lines))
        rooms = []

        for idx, poly in enumerate(polygons):
            if poly.area > 1.0:  # Игнорируем технологические микро-контуры менее 1 кв.м
                rooms.append({
                    'room_index': idx + 1,
                    'area_sqm': round(poly.area, 2),
                    'perimeter_m': round(poly.length, 2),
                    'centroid': (round(poly.centroid.x, 2), round(poly.centroid.y, 2)),
                    'polygon': poly
                })
        return rooms

    @staticmethod
    def check_line_of_sight(cam_pos: Tuple[float, float], target_pos: Tuple[float, float], wall_segments: List[LineString]) -> Dict[str, Any]:
        """Проверяет прямую видимость (Raycasting) от камеры до цели через стены."""
        ray = LineString([cam_pos, target_pos])
        obstructions = []

        for seg in wall_segments:
            if ray.crosses(seg):
                intersection = ray.intersection(seg)
                if not intersection.is_empty:
                    obstructions.append(intersection)

        is_visible = len(obstructions) == 0
        dist = math.sqrt((target_pos[0] - cam_pos[0])**2 + (target_pos[1] - cam_pos[1])**2)

        return {
            'is_visible': is_visible,
            'distance_m': round(dist, 2),
            'obstructions_count': len(obstructions)
        }


    @staticmethod
    def extract_points_by_layer(doc: ezdxf.document.Drawing, layer_name: str) -> List[Tuple[float, float]]:
        points = []
        msp = doc.modelspace()
        for e in msp.query(f'INSERT[layer=="{layer_name}"]'):
            points.append((round(float(e.dxf.insert.x), 2), round(float(e.dxf.insert.y), 2)))
        for e in msp.query(f'POINT[layer=="{layer_name}"]'):
            points.append((round(float(e.dxf.location.x), 2), round(float(e.dxf.location.y), 2)))
        return points
