import os, ezdxf, math

dxf_file = [f for f in os.listdir('.') if f.endswith('.dxf')][0]
doc = ezdxf.readfile(dxf_file)

print('АНАЛИЗ ПОЛИЛИНИЙ:')
print('='*60)

for layer_name in sorted(set(e.dxf.layer for e in doc.modelspace())):
    plines = [e for e in doc.modelspace() if e.dxf.layer == layer_name and e.dxftype() in ('LWPOLYLINE', 'POLYLINE')]
    
    if plines:
        print(f'\n{layer_name}: {len(plines)} полилиний')
        for i, pl in enumerate(plines[:3]):
            try:
                if pl.dxftype() == 'LWPOLYLINE':
                    points = list(pl.get_points())
                else:
                    points = list(pl.points())
                total_len = 0
                for j in range(len(points)-1):
                    dx = points[j+1][0] - points[j][0]
                    dy = points[j+1][1] - points[j][1]
                    total_len += math.sqrt(dx*dx + dy*dy)
                print(f'  #{i+1}: вершин={len(points)}, длина={total_len:.1f}мм')
            except Exception as ex:
                print(f'  #{i+1}: ошибка чтения точек ({ex})')
