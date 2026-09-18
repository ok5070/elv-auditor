"""
Главный скрипт импорта.
Запускает парсер DXF и сохраняет результат в JSON.
"""
import sys
import os
import json

# Добавляем корень проекта в путь
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.parser_dxf import DXFParser
from src.models import ProjectModel

def main():
    # Поиск DXF файла в текущей директории
    dxf_file = None
    for f in os.listdir('.'):
        if f.endswith('.dxf') or f.endswith('.DXF'):
            dxf_file = f
            break
    
    if not dxf_file:
        print("Ошибка: DXF файл не найден в текущей директории!")
        return
        
    print(f"Найден файл: {dxf_file}")

    print("="*50)
    print("ЗАПУСК IMPORT ENGINE v0.1")
    print("="*50)
    
    # Запуск парсера
    parser = DXFParser(dxf_file)
    project = parser.parse()
    
    # Сохранение результата
    output_file = "output/project_model.json"
    os.makedirs("output", exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(project.to_dict(), f, ensure_ascii=False, indent=2)
    
    print("\n" + "="*50)
    print(f"✓ УСПЕШНО! Модель сохранена в: {output_file}")
    print("="*50)
    print(f"Статистика:")
    print(f"  - Стен: {len(project.walls)}")
    print(f"  - Дверей: {len(project.doors)}")
    print(f"  - Оборудования: {len(project.equipment)}")
    print(f"  - Кабельных трасс: {len(project.cable_routes)}")
    print(f"  - Помещений: {len(project.rooms)}")
    print("="*50)

if __name__ == "__main__":
    main()
