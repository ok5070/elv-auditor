import ezdxf
import urllib.request
import json
import os

# 1. Генерируем тестовый DXF на диске: 12х6 м с 2 перегородками
doc = ezdxf.new("R2010")
msp = doc.modelspace()
msp.add_lwpolyline([(0, 0), (12, 0), (12, 6), (0, 6)], close=True, dxfattribs={"layer": "WALLS"})
msp.add_line((4, 0), (4, 6), dxfattribs={"layer": "WALLS"})
msp.add_line((8, 0), (8, 6), dxfattribs={"layer": "WALLS"})

dxf_file = "test_floorplan.dxf"
doc.saveas(dxf_file)
print(f"1. Чертеж {dxf_file} сформирован.")

# 2. Отправляем в микросервис
with open(dxf_file, "rb") as f:
    content = f.read()

boundary = "----BoundaryCadTest"
body = (
    f"--{boundary}\r\n"
    f'Content-Disposition: form-data; name="file"; filename="{dxf_file}"\r\n'
    f"Content-Type: application/dxf\r\n\r\n"
).encode("utf-8") + content + f"\r\n--{boundary}--\r\n".encode("utf-8")

req = urllib.request.Request(
    "http://127.0.0.1:8085/api/v1/audit/dxf",
    data=body,
    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
)

try:
    with urllib.request.urlopen(req) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        print("\n=== ОТВЕТ DXF ПАРСЕРА (API 200 OK) ===")
        print("Файл:", res.get("filename"))
        print("Стен обнаружено:", res.get("walls_detected"))
        print("Комнат распознано:", res.get("rooms_detected"))
        print("Суммарная площадь:", res.get("total_area_sqm"), "м²")
        for room in res.get("rooms", []):
            print(f"  * Помещение {room['room_index']}: S = {room['area_sqm']} м², P = {room['perimeter_m']} м, Центр = {room['centroid']}")
        print("======================================\n")
except Exception as e:
    print("Ошибка обращения к API:", e)
