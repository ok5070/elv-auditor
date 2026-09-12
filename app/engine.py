import math
from typing import List, Dict, Tuple
from app.schemas import AuditRequest, DoorInput, CameraInput, WifiAPInput, AudioZoneInput, Issue

class Engine:
    @staticmethod
    def audit_doors(doors: List[DoorInput]) -> Tuple[List[Issue], Dict[str, int]]:
        issues: List[Issue] = []
        bom: Dict[str, int] = {}

        def add_bom(name: str, count: int = 1):
            bom[name] = bom.get(name, 0) + count

        for d in doors:
            if d.is_fire_exit:
                add_bom("Замок электромагнитный (350 кг)")
            elif d.to_zone in ["server_room", "cash_desk"]:
                add_bom("Замок электромагнитный (500 кг) + ZL-планка")
            else:
                add_bom("Замок электромагнитный (280 кг)")

            add_bom("Дверной доводчик")
            add_bom("Магнитоконтактный датчик (СМК)")

            if d.to_zone == "server_room":
                add_bom("Биометрический терминал / Mifare (Вход)")
            else:
                add_bom("Считыватель карт Mifare (Вход)")

            if d.two_way_security:
                add_bom("Считыватель карт Mifare (Выход)")
            else:
                add_bom("Кнопка выхода сенсорная")

            if d.is_fire_exit:
                add_bom("Кнопка аварийной разблокировки ЭВАК (зеленая)")
                if d.width_mm < 900:
                    issues.append(Issue(
                        subsystem="СКУД",
                        severity="CRITICAL",
                        element=d.door_id,
                        msg=f"Ширина проема {d.width_mm} мм у́же нормы СП 1.13130 (минимум 900 мм)"
                    ))

        return issues, bom

    @staticmethod
    def audit_cameras(cameras: List[CameraInput], rack_pos, tray_h) -> Tuple[List[Issue], Dict[str, int], float]:
        issues: List[Issue] = []
        bom: Dict[str, int] = {}
        total_cable = 0.0

        for c in cameras:
            bom[f"IP-камера ({c.model})"] = bom.get(f"IP-камера ({c.model})", 0) + 1
            id_dist = (c.resolution_w * c.focal_length_mm) / (250 * c.sensor_w_mm)
            if c.dist_to_wall < 1.0:
                issues.append(Issue(
                    subsystem="СОТ",
                    severity="CRITICAL",
                    element=c.camera_id,
                    msg=f"Препятствие в {c.dist_to_wall} м блокирует обзор"
                ))
            elif c.dist_to_wall < id_dist * 0.5:
                issues.append(Issue(
                    subsystem="СОТ",
                    severity="WARNING",
                    element=c.camera_id,
                    msg=f"Дистанция до стены {c.dist_to_wall} м мала для оптики {c.focal_length_mm} мм"
                ))

            h_run = abs(c.pos.x - rack_pos.x) + abs(c.pos.y - rack_pos.y)
            v_run = abs(tray_h - c.pos.z) + abs(tray_h - rack_pos.z)
            cable_len = round((h_run + v_run + 2.5) * 1.10, 1)
            total_cable += cable_len

            if cable_len > 90.0:
                issues.append(Issue(
                    subsystem="СКС",
                    severity="CRITICAL",
                    element=c.camera_id,
                    msg=f"Трасса {cable_len} м превышает лимит ISO/IEC 11801 (90 м)"
                ))
            elif cable_len > 80.0:
                issues.append(Issue(
                    subsystem="СКС",
                    severity="WARNING",
                    element=c.camera_id,
                    msg=f"Трасса {cable_len} м близка к критическому пределу 90 м"
                ))

        return issues, bom, total_cable

    @staticmethod
    def audit_wifi(wifi_list: List[WifiAPInput]) -> Tuple[List[Issue], Dict[str, int]]:
        issues: List[Issue] = []
        bom: Dict[str, int] = {}
        wall_loss_map = {"drywall": 3.5, "brick": 8.0, "concrete": 15.0}

        for ap in wifi_list:
            bom[f"Точка доступа Wi-Fi ({ap.model})"] = bom.get(f"Точка доступа Wi-Fi ({ap.model})", 0) + 1
            d = max(ap.test_distance_m, 1.0)
            fspl = 20 * math.log10(d) + 20 * math.log10(ap.frequency_ghz * 1000) - 27.55
            wall_loss = ap.walls_crossed * wall_loss_map.get(ap.wall_material, 6.0)
            rssi = round(ap.tx_power_dbm - fspl - wall_loss, 1)

            if rssi < -75.0:
                issues.append(Issue(
                    subsystem="Wi-Fi",
                    severity="CRITICAL",
                    element=ap.ap_id,
                    msg=f"Сигнал в зоне '{ap.target_zone_name}' {rssi} dBm (критически слабее -75 dBm)"
                ))
            elif rssi < -65.0:
                issues.append(Issue(
                    subsystem="Wi-Fi",
                    severity="WARNING",
                    element=ap.ap_id,
                    msg=f"Сигнал в зоне '{ap.target_zone_name}' {rssi} dBm на грани нормы (-65 dBm)"
                ))

            if ap.target_zone_clients > 40:
                issues.append(Issue(
                    subsystem="Wi-Fi",
                    severity="WARNING",
                    element=ap.ap_id,
                    msg=f"Зона '{ap.target_zone_name}': {ap.target_zone_clients} клиентов. 1 AP перегрузится"
                ))

        return issues, bom

    @staticmethod
    def audit_audio(zones: List[AudioZoneInput]) -> Tuple[List[Issue], Dict[str, int]]:
        issues: List[Issue] = []
        bom: Dict[str, int] = {}

        for z in zones:
            h_work = max(z.ceiling_height_m - 1.5, 1.2)
            spacing = round(2 * h_work, 1)
            coverage = spacing * spacing * 0.8
            spk_count = math.ceil(z.area_sqm / coverage)

            if z.system_type == "100V":
                power_each = 6 if z.target_sound_pressure_db <= 75 else 10
                bom[f"Громкоговоритель потолочный 100V ({power_each} Вт)"] = (
                    bom.get(f"Громкоговоритель потолочный 100V ({power_each} Вт)", 0) + spk_count
                )
                amp_power = math.ceil(spk_count * power_each * 1.2)
                bom[f"Трансляционный усилитель 100V (~{amp_power} Вт)"] = 1
            else:
                imp = 8 if z.system_type == "LOW_Z_8OHM" else 16
                bom[f"Акустическая система Hi-Fi ({imp} Ом)"] = (
                    bom.get(f"Акустическая система Hi-Fi ({imp} Ом)", 0) + spk_count
                )
                if z.cable_distance_to_rack_m > 30:
                    issues.append(Issue(
                        subsystem="Аудио",
                        severity="WARNING",
                        element=z.zone_id,
                        msg=f"Трасса {z.cable_distance_to_rack_m} м велика для Low-Z. Нужен кабель 2х2.5 мм²"
                    ))

        return issues, bom
