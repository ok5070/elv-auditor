from fastapi.responses import FileResponse
from openpyxl.utils import get_column_letter
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
import openpyxl
from app.cad_converter import CADConverter
import os
import urllib.parse
import math
import io
import tempfile
import ezdxf
from fastapi import Form, Response, FastAPI, File, UploadFile, HTTPException
from fastapi.responses import Response, HTMLResponse, RedirectResponse, StreamingResponse
from app.excel_builder import generate_bom_excel
from app.schemas import AuditRequest, AuditResponse, Point2D, Point3D, WifiAPInput, AudioZoneInput, CameraInput, DoorInput
from app.engine import Engine
from app.report_builder import generate_html_report
from app.geometry_parser import GeometryParser
from app.geometry_export import build_geometry_export

app = FastAPI(
    title="ELV CAD-Auditor API",
    description="Микросервис аудита слаботочных систем (СКУД, СОТ, СКС, Wi-Fi, Аудио)",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

def process_audit(req: AuditRequest):
    all_issues = []
    bom = {}
    total_cable = 0.0

    d_issues, d_bom = Engine.audit_doors(req.doors)
    all_issues.extend(d_issues)
    bom.update(d_bom)

    c_issues, c_bom, c_cable = Engine.audit_cameras(req.cameras, req.rack_pos, req.ceiling_tray_height)
    all_issues.extend(c_issues)
    bom.update(c_bom)
    total_cable += c_cable

    w_issues, w_bom = Engine.audit_wifi(req.wifi_points)
    all_issues.extend(w_issues)
    bom.update(w_bom)

    a_issues, a_bom = Engine.audit_audio(req.audio_zones)
    all_issues.extend(a_issues)
    bom.update(a_bom)

    if total_cable > 0:
        bom["Кабель UTP Cat 5e 4x2x0.52 (бухты по 305м)"] = math.ceil(total_cable / 305)
        bom["Гофротруба ПВХ d=20мм с протяжкой (метры)"] = math.ceil(total_cable)
        bom["Клипса крепежная d=20мм (шт)"] = math.ceil(total_cable * 2)

    has_crit = any(i.severity == "CRITICAL" for i in all_issues)
    has_warn = any(i.severity == "WARNING" for i in all_issues)
    verdict = "REJECTED" if has_crit else ("WARNING" if has_warn else "APPROVED")

    return {
        "project": req.project_name,
        "client": req.client_name,
        "verdict": verdict,
        "cable_total_m": round(total_cable, 1),
        "issues": all_issues,
        "bom": bom
    }

@app.post("/api/v1/audit", response_model=AuditResponse, tags=["Audit"])
def audit_project(req: AuditRequest):
    data = process_audit(req)
    return AuditResponse(**data)

@app.post("/api/v1/audit/html", response_class=HTMLResponse, tags=["Reports"])
def audit_project_html(req: AuditRequest):
    data = process_audit(req)
    data_for_html = {
        "project": data["project"],
        "client": data["client"],
        "verdict": data["verdict"],
        "issues": [i.model_dump() for i in data["issues"]],
        "bom": data["bom"]
    }
    return HTMLResponse(content=generate_html_report(data_for_html))

@app.post("/api/v1/audit/dxf", tags=["CAD"])
async def audit_dxf_file(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".dxf"):
        raise HTTPException(status_code=400, detail="Поддерживаются только файлы с расширением .dxf")

    content = await file.read()
    try:
        doc = ezdxf.read(io.StringIO(content.decode("utf-8", errors="ignore")))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Ошибка разбора DXF структуры: {str(e)}")

    wall_segments = GeometryParser.extract_wall_segments(doc)
    rooms = GeometryParser.detect_rooms(wall_segments)

    rooms_summary = [
        {
            "room_index": r["room_index"],
            "area_sqm": r["area_sqm"],
            "perimeter_m": r["perimeter_m"],
            "centroid": r["centroid"]
        }
        for r in rooms
    ]

    return {
        "filename": file.filename,
        "walls_detected": len(wall_segments),
        "rooms_detected": len(rooms),
        "total_area_sqm": round(sum(r["area_sqm"] for r in rooms), 2),
        "rooms": rooms_summary
    }


@app.post("/api/v1/geometry/extract", tags=["CAD"])
async def extract_geometry_export(
    file: UploadFile = File(...),
    project_name: str = Form("Проект"),
):
    """Return a standalone geometry.v2 export without changing saved projects."""
    filename = file.filename or "drawing.dxf"
    extension = os.path.splitext(filename)[1].lower()
    if extension not in {".dxf", ".dwg"}:
        raise HTTPException(status_code=400, detail="Поддерживаются только файлы .dxf и .dwg")

    payload = await file.read(25 * 1024 * 1024 + 1)
    if len(payload) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Файл больше 25 МБ")
    if extension == ".dwg":
        try:
            payload = CADConverter.convert_dwg_to_dxf(payload, filename)
        except Exception as error:
            raise HTTPException(status_code=503, detail=f"Ошибка конвертации DWG: {error}") from error

    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as temporary:
            temporary.write(payload)
            temporary_path = temporary.name
        document = ezdxf.readfile(temporary_path)
        return build_geometry_export(document, filename, project_name)
    except (OSError, ezdxf.DXFError, UnicodeError) as error:
        raise HTTPException(status_code=422, detail=f"Не удалось прочитать CAD-файл: {error}") from error
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.remove(temporary_path)

@app.post("/api/v1/audit/excel", tags=["Reports"])
def audit_project_excel(req: AuditRequest):
    data = process_audit(req)
    excel_stream = generate_bom_excel(data["project"], data["client"], data["bom"])
    import urllib.parse
    clean_name = req.project_name.replace(' ', '_')
    encoded_name = urllib.parse.quote(f"BOM_{clean_name}.xlsx")
    return StreamingResponse(
        excel_stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"}
    )

@app.post("/api/v1/dxf/audit-excel", tags=["CAD Processing"])
def audit_cad_to_excel(
    file: UploadFile = File(...),
    project_name: str = Form("Комплексный проект CAD"),
    client_name: str = Form("ООО Сибест"),
    layer_walls: str = Form("WALLS,АР_СТЕНЫ,A-WALL,СТЕНЫ"),
    layer_wifi: str = Form("WIFI_AP,WI-FI,WIFI,ТОЧКИ_ДОСТУПА"),
    layer_cameras: str = Form("CAMERAS_CCTV,СОТ,ВИДЕО,CCTV,КАМЕРЫ"),
    layer_doors: str = Form("DOORS_ACS,СКУД,АР_ДВЕРИ,ДВЕРИ")
):
    filename = file.filename or "drawing.dxf"
    ext = os.path.splitext(filename)[1].lower()
    
    if ext not in [".dxf", ".dwg"]:
        raise HTTPException(status_code=400, detail="Поддерживаются только форматы .dxf и .dwg")

    raw_bytes = file.file.read()
    
    # 1. Автоконвертация DWG -> DXF при необходимости
    if ext == ".dwg":
        try:
            dxf_bytes = CADConverter.convert_dwg_to_dxf(raw_bytes, filename)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Ошибка конвертации DWG: {str(e)}")
    else:
        dxf_bytes = raw_bytes

    temp_path = f"/tmp/temp_cad_{os.getpid()}_{os.path.splitext(filename)[0]}.dxf"
    with open(temp_path, "wb") as f:
        f.write(dxf_bytes)

    try:
        doc = ezdxf.readfile(temp_path)
        
        # Функция подбора первого существующего слоя из списка синонимов
        existing_layers = {layer.dxf.name.lower(): layer.dxf.name for layer in doc.layers}
        def resolve_layer(candidates_str: str) -> list[str]:
            res = []
            for item in candidates_str.split(","):
                name = item.strip()
                if name.lower() in existing_layers:
                    res.append(existing_layers[name.lower()])
            return res

        matched_walls = resolve_layer(layer_walls) or ["WALLS"]
        matched_wifi = resolve_layer(layer_wifi)
        matched_cams = resolve_layer(layer_cameras)
        matched_doors = resolve_layer(layer_doors)

        segs = GeometryParser.extract_wall_segments(doc, target_layers=matched_walls)
        detected_rooms = GeometryParser.detect_rooms(segs)

        wifi_pts = []
        for l in (matched_wifi or ["WIFI_AP"]):
            wifi_pts.extend(GeometryParser.extract_points_by_layer(doc, l))

        cam_pts = []
        for l in (matched_cams or ["CAMERAS_CCTV"]):
            cam_pts.extend(GeometryParser.extract_points_by_layer(doc, l))

        door_pts = []
        for l in (matched_doors or ["DOORS_ACS"]):
            door_pts.extend(GeometryParser.extract_points_by_layer(doc, l))

    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    # 2. Формируем расчетные зоны Аудио
    audio_zones = []
    for idx, room in enumerate(detected_rooms, 1):
        area = float(room.get("area_sqm", 0.0))
        cx, cy = room.get("centroid", (0.0, 0.0))
        if area > 5.0:
            dist = float(round(max(abs(cx), abs(cy)) * 1.3, 1))
            audio_zones.append(
                AudioZoneInput(
                    zone_id=f"AZ-{idx:02d}",
                    name=f"Помещение {idx}",
                    area_sqm=round(area, 1),
                    ceiling_height_m=3.0,
                    system_type="100V",
                    cable_distance_to_rack_m=dist
                )
            )

    # 3. Wi-Fi точки
    wifi_points = []
    if wifi_pts:
        for idx, (wx, wy) in enumerate(wifi_pts, 1):
            wifi_points.append(
                WifiAPInput(
                    ap_id=f"AP-{idx:02d}",
                    pos=Point2D(x=float(wx), y=float(wy)),
                    target_zone_name=f"Зона покрытия {idx}",
                    target_zone_clients=25,
                    test_distance_m=8.0
                )
            )
    else:
        for idx, room in enumerate(detected_rooms, 1):
            area = float(room.get("area_sqm", 0.0))
            cx, cy = room.get("centroid", (0.0, 0.0))
            if area > 15.0:
                wifi_points.append(
                    WifiAPInput(
                        ap_id=f"AP-{idx:02d}",
                        pos=Point2D(x=float(cx), y=float(cy)),
                        target_zone_name=f"Помещение {idx}",
                        target_zone_clients=min(int(area / 4) + 2, 40),
                        test_distance_m=round(max((area ** 0.5) / 2.0, 2.0), 1)
                    )
                )

    # 4. Камеры СОТ
    cameras = []
    for idx, (cx, cy) in enumerate(cam_pts, 1):
        cameras.append(
            CameraInput(
                camera_id=f"CAM-{idx:02d}",
                model="IP 2MP 2.8mm",
                pos=Point3D(x=float(cx), y=float(cy), z=2.8),
                dist_to_wall=0.1
            )
        )

    # 5. Двери СКУД
    doors = []
    for idx, (dx, dy) in enumerate(door_pts, 1):
        doors.append(
            DoorInput(
                door_id=f"D-{idx:02d}",
                width_mm=900,
                is_fire_exit=False,
                from_zone="Коридор",
                to_zone=f"Помещение {idx}",
                two_way_security=False
            )
        )

    req = AuditRequest(
        project_name=project_name,
        client_name=client_name,
        rack_pos=Point3D(x=0.0, y=0.0, z=2.0),
        ceiling_tray_height=3.2,
        doors=doors,
        cameras=cameras,
        wifi_points=wifi_points,
        audio_zones=audio_zones
    )

    data = process_audit(req)
    excel_stream = generate_bom_excel(data["project"], data["client"], data["bom"])
    excel_stream.seek(0)

    clean_name = project_name.replace(" ", "_")
    encoded_name = urllib.parse.quote(f"BOM_{clean_name}.xlsx")
    return Response(
        content=excel_stream.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"}
    )


PRICE_CATALOG = {
    # Оборудование и монтаж (руб.)
    "Замок электромагнитный (280 кг)": {"eq": 4200.0, "work": 2200.0},
    "Дверной доводчик": {"eq": 3400.0, "work": 1200.0},
    "Магнитоконтактный датчик (СМК)": {"eq": 450.0, "work": 600.0},
    "Считыватель карт Mifare (Вход)": {"eq": 2900.0, "work": 1500.0},
    "Кнопка выхода сенсорная": {"eq": 1750.0, "work": 900.0},
    "IP-камера (IP 2MP 2.8mm)": {"eq": 7200.0, "work": 2500.0},
    "Точка доступа Wi-Fi (Ceiling AP Wi-Fi 6)": {"eq": 14800.0, "work": 2000.0},
    "Громкоговоритель потолочный 100V (6 Вт)": {"eq": 2100.0, "work": 1100.0},
    "Трансляционный усилитель 100V (~144 Вт)": {"eq": 39500.0, "work": 6500.0},
    "Трансляционный усилитель 100V (~87 Вт)": {"eq": 29000.0, "work": 5000.0},
    "Трансляционный усилитель 100V (~36 Вт)": {"eq": 19500.0, "work": 4000.0},
    "Кабель UTP Cat 5e 4x2x0.52 (бухты по 305м)": {"eq": 11900.0, "work": 0.0},
    "Гофротруба ПВХ d=20мм с протяжкой (метры)": {"eq": 28.0, "work": 65.0},
    "Клипса крепежная d=20мм (шт)": {"eq": 4.5, "work": 0.0}
}

def generate_bom_excel(project_name: str, client_name: str, bom_items: list) -> io.BytesIO:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Коммерческое предложение"
    ws.views.sheetView[0].showGridLines = True

    title_font = Font(name="Calibri", size=14, bold=True, color="1F497D")
    meta_font = Font(name="Calibri", size=11, bold=True)
    header_font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="2F5597", end_color="2F5597", fill_type="solid")
    total_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
    grand_fill = PatternFill(start_color="B4C6E7", end_color="B4C6E7", fill_type="solid")

    thin_border = Border(
        left=Side(style="thin", color="D9D9D9"),
        right=Side(style="thin", color="D9D9D9"),
        top=Side(style="thin", color="D9D9D9"),
        bottom=Side(style="thin", color="D9D9D9")
    )
    thick_bottom = Border(bottom=Side(style="medium", color="2F5597"))

    ws["A1"] = f"Коммерческое предложение: {project_name}"
    ws["A1".strip()].font = title_font
    ws["A2"] = f"Заказчик: {client_name}"
    ws["A2".strip()].font = meta_font

    headers = [
        "№", "Наименование позиции", "Кол-во", "Ед.",
        "Цена оборуд. (₽)", "Сумма оборуд. (₽)",
        "Монтаж за ед. (₽)", "Сумма монтажа (₽)",
        "Итого по позиции (₽)"
    ]
    
    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=4, column=col_idx, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = thin_border
    ws.row_dimensions[4].height = 28

    current_row = 5
    for idx, item in enumerate(bom_items, 1):
        if isinstance(item, dict):
            name = item.get("name") or item.get("item") or item.get("title")
            if not name:
                # случай формата {название: кол-во}
                name, val = next(iter(item.items()))
                qty = float(val) if not isinstance(val, dict) else float(val.get("qty", 1))
            else:
                qty = float(item.get("qty", item.get("quantity", 1)))
            unit = item.get("unit", "шт")
        elif isinstance(item, (list, tuple)):
            name = str(item[0])
            qty = float(item[1]) if len(item) > 1 else 1.0
            unit = str(item[2]) if len(item) > 2 else "шт"
        else:
            # если пришла строка
            raw_str = str(item)
            if ":" in raw_str:
                parts = raw_str.split(":", 1)
                name = parts[0].strip()
                val_part = parts[1].strip().split()
                try:
                    qty = float(val_part[0])
                except (ValueError, IndexError):
                    qty = 1.0
                unit = val_part[1] if len(val_part) > 1 else "шт"
            else:
                name = raw_str
                qty = 1.0
                unit = "шт"
        
        rates = PRICE_CATALOG.get(name, {"eq": 1000.0, "work": 500.0})
        p_eq = rates["eq"]
        p_wrk = rates["work"]

        ws.cell(row=current_row, column=1, value=idx).alignment = Alignment(horizontal="center")
        ws.cell(row=current_row, column=2, value=name).alignment = Alignment(horizontal="left")
        ws.cell(row=current_row, column=3, value=qty).alignment = Alignment(horizontal="center")
        ws.cell(row=current_row, column=4, value=unit).alignment = Alignment(horizontal="center")
        
        # Финансовые колонки
        c_peq = ws.cell(row=current_row, column=5, value=p_eq)
        c_peq.number_format = "#,##0.00"
        
        c_seq = ws.cell(row=current_row, column=6, value=f"=C{current_row}*E{current_row}")
        c_seq.number_format = "#,##0.00"

        c_pwrk = ws.cell(row=current_row, column=7, value=p_wrk)
        c_pwrk.number_format = "#,##0.00"

        c_swrk = ws.cell(row=current_row, column=8, value=f"=C{current_row}*G{current_row}")
        c_swrk.number_format = "#,##0.00"

        c_tot = ws.cell(row=current_row, column=9, value=f"=F{current_row}+H{current_row}")
        c_tot.number_format = "#,##0.00"
        c_tot.font = Font(bold=True)

        for col in range(1, 10):
            ws.cell(row=current_row, column=col).border = thin_border
        current_row += 1

    last_item_row = current_row - 1

    # Подвальные итоги
    def add_total_row(label, formula_val, is_grand=False):
        nonlocal current_row
        ws.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=8)
        c_lbl = ws.cell(row=current_row, column=1, value=label)
        c_lbl.font = Font(bold=True, size=11 if is_grand else 10)
        c_lbl.alignment = Alignment(horizontal="right", vertical="center")
        
        c_val = ws.cell(row=current_row, column=9, value=formula_val)
        c_val.font = Font(bold=True, size=11 if is_grand else 10)
        c_val.number_format = "#,##0.00"
        c_val.alignment = Alignment(horizontal="right", vertical="center")

        fill = grand_fill if is_grand else total_fill
        for c in range(1, 10):
            cell = ws.cell(row=current_row, column=c)
            cell.fill = fill
            cell.border = thin_border
        ws.row_dimensions[current_row].height = 22
        current_row += 1

    row_eq_total = current_row
    add_total_row("ИТОГО ОБОРУДОВАНИЕ:", f"=SUM(F5:F{last_item_row})")
    
    row_wrk_total = current_row
    add_total_row("ИТОГО МОНТАЖНЫЕ РАБОТЫ:", f"=SUM(H5:H{last_item_row})")
    
    row_pnr_total = current_row
    add_total_row("Пусконаладка и проектные работы (10% от работ):", f"=I{row_wrk_total}*0.1")
    
    row_mat_total = current_row
    add_total_row("Расходные и крепежные материалы (3% от оборудования):", f"=I{row_eq_total}*0.03")

    add_total_row("ВСЕГО ПО СМЕТЕ (руб.):", f"=I{row_eq_total}+I{row_wrk_total}+I{row_pnr_total}+I{row_mat_total}", is_grand=True)

    # Автоширина колонок
    col_widths = {1: 6, 2: 46, 3: 10, 4: 8, 5: 18, 6: 20, 7: 18, 8: 20, 9: 22}
    for col_idx, width in col_widths.items():
        col_letter = get_column_letter(col_idx)
        ws.column_dimensions[col_letter].width = width

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output


@app.get("/", include_in_schema=False)
async def serve_dashboard():
    return FileResponse("app/static/index.html")
