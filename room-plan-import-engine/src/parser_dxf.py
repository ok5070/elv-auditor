"""
Парсер DXF файлов для извлечения архитектурных данных и оборудования.
Адаптирован под структуру файлов ХИКВ (СОТ, СКУД, ПОЖАРНАЯ сигнализация).
"""
import ezdxf
from typing import List, Dict, Any, Tuple
from src.models import ProjectModel, Wall, Door, Equipment, CableRoute, Room, Point
import math

class DXFParser:
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.doc = None
        self.modelspace = None
        self.project = ProjectModel()
        
        # Слои для распознавания (на основе анализа вашего файла)
        self.wall_layers = ['ПЛАН', 'WALL', '0', 'ARCH', 'СТЕНЫ', 'PLAN']
        self.door_layers = ['ДВЕРИ', 'DOOR', 'ОКНА', 'WINDOW', 'ПРОЕМЫ', 'ARC']  # Двери часто как дуги
        self.equipment_layers = ['ОБОРУДОВАНИЕ', 'СОТ', 'FIRE_ALARM', 'SOZP', 'EQUIPMENT', 'CAMERA', '_FIRE_ALARM_LINE']
        self.cable_layers = ['ТРАССЫ', 'CABLE', 'КАБЕЛИ', 'WIRE', 'MAGISTRAL', 'SOZP', '_FIRE_ALARM_LINE']
        
    def load(self):
        """Загрузка DXF файла"""
        try:
            self.doc = ezdxf.readfile(self.filepath)
            self.modelspace = self.doc.modelspace()
            print(f"✓ Файл загружен: {self.filepath}")
            print(f"  Версия DXF: {self.doc.dxfversion}")
            return True
        except Exception as e:
            print(f"✗ Ошибка загрузки файла: {e}")
            return False
    
    def _get_layer_name(self, entity) -> str:
        """Получение имени слоя с учетом кодировки"""
        try:
            layer = entity.dxf.layer
            # Попытка декодирования если нужно
            if isinstance(layer, bytes):
                return layer.decode('utf-8', errors='ignore')
            return str(layer)
        except:
            return ""
    
    def _is_in_layers(self, layer_name: str, target_layers: List[str]) -> bool:
        """Проверка принадлежности слоя к списку целевых"""
        layer_upper = layer_name.upper()
        for target in target_layers:
            if target.upper() in layer_upper or layer_upper in target.upper():
                return True
        return False

    def extract_walls(self) -> List[Wall]:
        """Извлечение стен из линий и полилиний"""
        walls = []
        print("\n--- Извлечение стен ---")
        
        for entity in self.modelspace:
            layer = self._get_layer_name(entity)
            
            # Берем ТОЛЬКО слой ПЛАН для стен (исключаем мусор с других слоев)
            if layer.upper() != 'ПЛАН':
                continue
                
            try:
                if entity.dxftype() == 'LINE':
                    start = Point(entity.dxf.start.x, entity.dxf.start.y)
                    end = Point(entity.dxf.end.x, entity.dxf.end.y)
                    
                    # Пропускаем очень короткие линии (размерные, выноски)
                    # В данном файле стены нарисованы короткими сегментами, поэтому порог 50мм
                    length = math.sqrt((end.x - start.x)**2 + (end.y - start.y)**2)
                    if length < 50: # Минимальная длина стены в мм
                        continue
                        
                    wall = Wall(start=start, end=end, layer=layer)
                    walls.append(wall)
                    
                elif entity.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
                    # Разбиваем полилинию на сегменты стен
                    # ВАЖНО: используем get_points() вместо points()
                    points = list(entity.get_points())
                    for i in range(len(points) - 1):
                        p1 = points[i]
                        p2 = points[i+1]
                        start = Point(p1[0], p1[1])
                        end = Point(p2[0], p2[1])
                        
                        length = math.sqrt((end.x - start.x)**2 + (end.y - start.y)**2)
                        if length < 50: # Минимальная длина стены в мм
                            continue
                            
                        wall = Wall(start=start, end=end, layer=layer)
                        walls.append(wall)
                        
            except Exception as e:
                print(f"  Ошибка обработки объекта: {e}")
                continue
        
        self.project.walls = walls
        print(f"  Найдено стен: {len(walls)}")
        return walls

    def extract_doors(self) -> List[Door]:
        """Извлечение дверей (пока заглушка, требует доработки под блоки)"""
        doors = []
        print("\n--- Извлечение дверей ---")
        # В реальных файлах двери часто являются блоками или дугами
        # Здесь упрощенная логика
        self.project.doors = doors
        print(f"  Найдено дверей: {len(doors)} (требуется доработка распознавания блоков)")
        return doors

    def extract_equipment(self) -> List[Equipment]:
        """Извлечение оборудования (камеры, датчики, сирены)"""
        equipment_list = []
        print("\n--- Извлечение оборудования ---")
        
        for entity in self.modelspace:
            layer = self._get_layer_name(entity)
            
            if not self._is_in_layers(layer, self.equipment_layers):
                continue
            
            try:
                if entity.dxftype() == 'INSERT': # Блок
                    block_name = entity.dxf.name
                    pos = Point(entity.dxf.insert.x, entity.dxf.insert.y)
                    
                    # Определение типа оборудования по имени блока или слою
                    eq_type = "unknown"
                    layer_upper = layer.upper()
                    block_upper = block_name.upper()
                    
                    if 'CAM' in block_upper or 'CAMERA' in layer_upper or 'СОТ' in layer_upper:
                        eq_type = "camera"
                    elif 'FIRE' in block_upper or 'SENSOR' in block_upper or 'FIRE_ALARM' in layer_upper:
                        eq_type = "fire_sensor"
                    elif 'SIREN' in block_upper or 'SOZP' in layer_upper:
                        eq_type = "siren"
                    elif 'ACCESS' in block_upper or 'СКУД' in layer_upper:
                        eq_type = "access_reader"
                    
                    eq = Equipment(
                        name=block_name,
                        type=eq_type,
                        position=pos,
                        layer=layer,
                        block_name=block_name
                    )
                    equipment_list.append(eq)
                    
            except Exception as e:
                continue
        
        self.project.equipment = equipment_list
        print(f"  Найдено единиц оборудования: {len(equipment_list)}")
        return equipment_list

    def extract_cable_routes(self) -> List[CableRoute]:
        """Извлечение кабельных трасс"""
        routes = []
        print("\n--- Извлечение кабельных трасс ---")
        
        for entity in self.modelspace:
            layer = self._get_layer_name(entity)
            
            if not self._is_in_layers(layer, self.cable_layers):
                continue
            
            try:
                if entity.dxftype() == 'LINE' or entity.dxftype() == 'POLYLINE' or entity.dxftype() == 'LWPOLYLINE':
                    points = []
                    total_length = 0.0
                    
                    if entity.dxftype() == 'LINE':
                        p_start = entity.dxf.start
                        p_end = entity.dxf.end
                        points = [Point(p_start.x, p_start.y), Point(p_end.x, p_end.y)]
                        total_length = math.sqrt((p_end.x - p_start.x)**2 + (p_end.y - p_start.y)**2)
                    else:
                        verts = list(entity.points())
                        for v in verts:
                            points.append(Point(v[0], v[1]))
                        
                        for i in range(len(points) - 1):
                            p1 = points[i]
                            p2 = points[i+1]
                            seg_len = math.sqrt((p2.x - p1.x)**2 + (p2.y - p1.y)**2)
                            total_length += seg_len
                    
                    if len(points) > 1:
                        route = CableRoute(
                            points=points,
                            layer=layer,
                            cable_type="data", # Можно уточнять по слою
                            length=total_length
                        )
                        routes.append(route)
                        
            except Exception as e:
                continue
        
        self.project.cable_routes = routes
        print(f"  Найдено кабельных трасс: {len(routes)}")
        return routes

    def parse(self) -> ProjectModel:
        """Основной метод парсинга"""
        if not self.load():
            return self.project
        
        # Извлекаем имя файла как название проекта
        import os
        filename = os.path.basename(self.filepath)
        self.project.name = filename.replace('.dxf', '').replace('.DWG', '')
        self.project.floor = "3 этаж" # Можно распознать из имени файла
        
        self.extract_walls()
        self.extract_doors()
        self.extract_equipment()
        self.extract_cable_routes()
        
        return self.project
