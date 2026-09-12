import urllib.request
import json

payload = {
    "project_name": "Комплексный аудит (Все 5 систем)",
    "client_name": "ООО Сибест",
    "rack_pos": {"x": 2.0, "y": 2.0, "z": 1.8},
    "ceiling_tray_height": 3.2,
    "doors": [
        {"door_id": "D-FIRE", "width_mm": 820, "is_fire_exit": True, "from_zone": "hall", "to_zone": "street", "two_way_security": False}
    ],
    "cameras": [
        {"camera_id": "CAM-BLIND", "model": "IP 2MP 2.8mm", "sensor_w_mm": 5.12, "resolution_w": 1920, "focal_length_mm": 2.8, "pos": {"x": 3.0, "y": 2.0, "z": 2.8}, "dist_to_wall": 0.6},
        {"camera_id": "CAM-FAR", "model": "IP 4MP 4.0mm", "sensor_w_mm": 5.12, "resolution_w": 2560, "focal_length_mm": 4.0, "pos": {"x": 65.0, "y": 30.0, "z": 3.5}, "dist_to_wall": 12.0}
    ],
    "wifi_points": [
        {"ap_id": "AP-01", "model": "Ceiling Wi-Fi 6", "tx_power_dbm": 20.0, "pos": {"x": 5.0, "y": 5.0}, "frequency_ghz": 5.0, "target_zone_name": "Конференц-зал", "target_zone_clients": 65, "wall_material": "concrete", "walls_crossed": 2, "test_distance_m": 15.0}
    ],
    "audio_zones": [
        {"zone_id": "AUDIO-BAR", "name": "Барная зона", "area_sqm": 80.0, "ceiling_height_m": 3.5, "system_type": "LOW_Z_16OHM", "target_sound_pressure_db": 82, "cable_distance_to_rack_m": 45.0}
    ]
}

req = urllib.request.Request(
    "http://127.0.0.1:8085/api/v1/audit",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"}
)

try:
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        print("\n=== РЕЗУЛЬТАТ ПРОВЕРКИ ФАЗЫ 2 ===")
        print(f"Статус ответа: {resp.status} OK")
        print(f"Вердикт проекта: {data['verdict']}")
        print(f"Общий метраж кабеля СКС: {data['cable_total_m']} м")
        print(f"\nОбнаруженные коллизии ({len(data['issues'])} шт.):")
        for i in data['issues']:
            print(f"  * [{i['severity']}] [{i['subsystem']}] {i['element']}: {i['msg']}")
        print("\nСформированная спецификация (BOM):")
        for k, v in data['bom'].items():
            print(f"  - {k}: {v}")
        print("==================================\n")
except Exception as e:
    print(f"Ошибка вызова API: {e}")
