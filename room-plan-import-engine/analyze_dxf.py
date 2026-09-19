#!/usr/bin/env python3
"""
Анализ DXF файла для понимания структуры чертежа
"""
import ezdxf
import os
import json

def analyze_dxf(filename):
    print(f"Анализ файла: {filename}")
    print("=" * 60)
    
    # Читаем файл
    doc = ezdxf.readfile(filename)
    msp = doc.modelspace()
    
    # 1. Слои
    print("\n=== СЛОИ (LAYERS) ===")
    layers = list(doc.layers)
    print(f"Всего слоев: {len(layers)}")
    for layer in layers:
        print(f"  - '{layer.dxf.name}' (цвет: {layer.dxf.color})")
    
    # 2. Типы объектов
    print("\n=== ТИПЫ ОБЪЕКТОВ В MODELSPACE ===")
    entity_counts = {}
    for entity in msp:
        t = entity.dxftype()
        entity_counts[t] = entity_counts.get(t, 0) + 1
    
    for t, count in sorted(entity_counts.items(), key=lambda x: -x[1]):
        print(f"  {t}: {count}")
    
    # 3. Примеры объектов по слоям
    print("\n=== ПРИМЕРЫ ОБЪЕКТОВ ПО СЛОЯМ ===")
    layer_samples = {}
    for entity in msp:
        layer = entity.dxf.layer
        if layer not in layer_samples:
            layer_samples[layer] = entity
    
    for layer, entity in sorted(layer_samples.items())[:15]:
        t = entity.dxftype()
        print(f"\n--- Слой: '{layer}', Тип: {t} ---")
        try:
            if t == 'LWPOLYLINE':
                points = list(entity.points())
                print(f"  Вершин: {len(points)}")
                if len(points) > 0:
                    print(f"  Первая точка: {points[0]}")
                    if len(points) > 1:
                        print(f"  Вторая точка: {points[1]}")
                        # Длина первого сегмента
                        dx = points[1][0] - points[0][0]
                        dy = points[1][1] - points[0][1]
                        length = (dx**2 + dy**2)**0.5
                        print(f"  Длина первого сегмента: {length:.2f}")
            elif t == 'LINE':
                start = entity.dxf.start
                end = entity.dxf.end
                print(f"  Start: ({start[0]:.2f}, {start[1]:.2f})")
                print(f"  End: ({end[0]:.2f}, {end[1]:.2f})")
                length = ((end[0]-start[0])**2 + (end[1]-start[1])**2)**0.5
                print(f"  Длина: {length:.2f}")
            elif t == 'INSERT':
                print(f"  Блок: '{entity.dxf.name}'")
                print(f"  Позиция: ({entity.dxf.insert[0]:.2f}, {entity.dxf.insert[1]:.2f})")
                if hasattr(entity.dxf, 'rotation'):
                    print(f"  Поворот: {entity.dxf.rotation}°")
                if hasattr(entity.dxf, 'xscale'):
                    print(f"  Масштаб X: {entity.dxf.xscale}, Y: {entity.dxf.yscale}")
            elif t == 'CIRCLE':
                print(f"  Центр: ({entity.dxf.center[0]:.2f}, {entity.dxf.center[1]:.2f})")
                print(f"  Радиус: {entity.dxf.radius:.2f}")
            elif t in ('TEXT', 'MTEXT'):
                text = entity.dxf.text if hasattr(entity.dxf, 'text') else 'N/A'
                print(f"  Текст: {str(text)[:80]}")
            elif t == 'POLYLINE':
                print(f"  3D полилиния, вершин: {len(list(entity.points()))}")
        except Exception as e:
            print(f"  Ошибка чтения: {e}")
    
    # 4. Блоки
    print("\n=== БЛОКИ (BLOCKS) ===")
    blocks = list(doc.blocks)
    print(f"Всего блоков: {len(blocks)}")
    
    # Группируем блоки по имени
    block_names = {}
    for block in blocks:
        name = block.name
        if name not in block_names:
            block_names[name] = 0
        block_names[name] += 1
    
    # Показываем уникальные имена блоков и сколько раз встречаются
    print("\nУникальные имена блоков:")
    for name, count in sorted(block_names.items(), key=lambda x: -x[1])[:30]:
        # Находим сам блок чтобы посмотреть содержимое
        try:
            block_obj = doc.blocks.get(name)
            entities_in_block = list(block_obj)
            types_in_block = {}
            for e in entities_in_block:
                t = e.dxftype()
                types_in_block[t] = types_in_block.get(t, 0) + 1
            
            types_str = ', '.join([f"{t}:{c}" for t,c in types_in_block.items()])
            print(f"  '{name}': {count} вхождений, внутри: [{types_str}]")
        except:
            print(f"  '{name}': {count} вхождений")
    
    if len(block_names) > 30:
        print(f"  ... и ещё {len(block_names) - 30} типов блоков")
    
    # 5. Единицы измерения
    print("\n=== ЕДИНИЦЫ ИЗМЕРЕНИЯ ===")
    try:
        units = doc.header.get('$INSUNITS', 0)
        units_map = {
            0: "Без единиц",
            1: "Дюймы",
            2: "Футы",
            3: "Мили",
            4: "Миллиметры",
            5: "Сантиметры",
            6: "Метры",
            7: "Километры",
            8: "Микроины",
            9: "Милы",
            10: "Нанометры",
            11: "Пикометры"
        }
        print(f"Единицы чертежа: {units_map.get(units, f'Неизвестно ({units})')}")
    except Exception as e:
        print(f"Не удалось определить единицы: {e}")
    
    # 6. Границы чертежа
    print("\n=== ГРАНИЦЫ ЧЕРТЕЖА ===")
    try:
        extmin = doc.header.get('$EXTMIN', (0, 0, 0))
        extmax = doc.header.get('$EXTMAX', (0, 0, 0))
        print(f"Min: ({extmin[0]:.2f}, {extmin[1]:.2f})")
        print(f"Max: ({extmax[0]:.2f}, {extmax[1]:.2f})")
        width = extmax[0] - extmin[0]
        height = extmax[1] - extmin[1]
        print(f"Ширина: {width:.2f}, Высота: {height:.2f}")
    except Exception as e:
        print(f"Не удалось определить границы: {e}")

if __name__ == "__main__":
    # Ищем DXF файлы в текущей директории
    dxf_files = [f for f in os.listdir('.') if f.lower().endswith('.dxf')]
    
    if not dxf_files:
        print("DXF файлы не найдены в текущей директории")
        exit(1)
    
    print(f"Найдено DXF файлов: {len(dxf_files)}")
    for f in dxf_files:
        print(f"  - {f}")
    
    # Анализируем первый файл
    if dxf_files:
        analyze_dxf(dxf_files[0])
