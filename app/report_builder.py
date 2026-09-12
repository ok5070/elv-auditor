def generate_html_report(data: dict) -> str:
    badge_colors = {
        "APPROVED": ("#10b981", "ПРОЕКТ ОДОБРЕН (APPROVED)"),
        "WARNING": ("#f59e0b", "ТРЕБУЮТСЯ КОРРЕКТИРОВКИ (WARNING)"),
        "REJECTED": ("#ef4444", "ОШИБКИ ПРОЕКТИРОВАНИЯ (REJECTED)")
    }
    color, text = badge_colors[data["verdict"]]

    issues_rows = "".join([
        f"""<tr>
            <td style='padding:8px; border-bottom:1px solid #e5e7eb;'><b style='color:{'#ef4444' if i['severity']=='CRITICAL' else '#f59e0b'};'>{i['severity']}</b></td>
            <td style='padding:8px; border-bottom:1px solid #e5e7eb;'>{i['subsystem']}</td>
            <td style='padding:8px; border-bottom:1px solid #e5e7eb;'><code>{i['element']}</code></td>
            <td style='padding:8px; border-bottom:1px solid #e5e7eb;'>{i['msg']}</td>
        </tr>""" for i in data["issues"]
    ]) or "<tr><td colspan='4' style='padding:12px; color:#10b981;'>Нарушений не обнаружено.</td></tr>"

    bom_rows = "".join([
        f"<tr><td style='padding:8px; border-bottom:1px solid #e5e7eb;'>{item}</td><td style='padding:8px; border-bottom:1px solid #e5e7eb; font-weight:bold; text-align:right;'>{cnt}</td></tr>"
        for item, cnt in data["bom"].items()
    ])

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Аудит: {data['project']}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background:#f9fafb; margin:0; padding:24px; color:#1f2937; }}
        .container {{ max-width: 900px; margin: 0 auto; background: #fff; padding: 32px; border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); }}
        .header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #f3f4f6; padding-bottom: 16px; margin-bottom: 24px; }}
        .badge {{ background:{color}; color:#fff; padding:8px 16px; border-radius:6px; font-weight:bold; font-size:14px; }}
        table {{ width:100%; border-collapse:collapse; margin-top:12px; font-size:14px; }}
        th {{ background:#f3f4f6; text-align:left; padding:8px; }}
        h2 {{ font-size:18px; margin-top:28px; border-left:4px solid #3b82f6; padding-left:8px; }}
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <div>
            <h1 style="margin:0; font-size:22px;">Инженерный аудит слаботочных систем</h1>
            <p style="margin:4px 0 0 0; color:#6b7280;">Объект: <b>{data['project']}</b> | Заказчик: <b>{data['client']}</b></p>
        </div>
        <div class="badge">{text}</div>
    </div>
    <h2>1. Реестр замечаний и коллизий</h2>
    <table>
        <thead><tr><th>Уровень</th><th>Система</th><th>Элемент</th><th>Замечание / Нарушение норм</th></tr></thead>
        <tbody>{issues_rows}</tbody>
    </table>
    <h2>2. Сводная спецификация оборудования и материалов</h2>
    <table>
        <thead><tr><th>Наименование позиции</th><th style="text-align:right;">Количество</th></tr></thead>
        <tbody>{bom_rows}</tbody>
    </table>
</div>
</body>
</html>"""
