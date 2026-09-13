import math
from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional
from pydantic import BaseModel, Field, field_validator

Point2D = Tuple[float, float]
Segment2D = Tuple[Point2D, Point2D]


class ConsolidationParams(BaseModel):
    k: float = Field(
        default=0.1,
        description="Масштаб калибровки: метров на единицу CAD (строго > 0)",
    )
    min_wall_length_m: float = Field(
        default=0.05,
        description="Порог отсечения микросегментов и геометрического шума в метрах (50 мм)",
    )
    eps_snap_m: float = Field(
        default=0.05,
        description="Максимальный технологический зазор для слияния фрагментов стены (50 мм)",
    )
    door_gap_min_m: float = Field(
        default=0.60,
        description="Нижняя граница ширины защищаемого дверного/технологического проема (600 мм)",
    )
    door_gap_max_m: float = Field(
        default=1.50,
        description="Верхняя граница ширины защищаемого дверного/технологического проема (1500 мм)",
    )
    angle_tolerance_deg: float = Field(
        default=2.0,
        description="Угловой допуск коллинеарности отрезков в градусах",
    )
    lateral_offset_m: float = Field(
        default=0.03,
        description="Максимальное боковое смещение продольных осей (30 мм)",
    )
    tl_snap_radius_m: float = Field(
        default=0.08,
        description="Радиус поиска и дотяжки T/L-сопряжений (80 мм)",
    )

    @field_validator("k")
    @classmethod
    def validate_k_positive(cls, v: float) -> float:
        if v <= 0.0:
            raise ValueError(f"Коэффициент масштабирования k должен быть строго > 0, получено: {v}")
        return v

    @field_validator(
        "min_wall_length_m",
        "eps_snap_m",
        "door_gap_min_m",
        "door_gap_max_m",
        "angle_tolerance_deg",
        "lateral_offset_m",
        "tl_snap_radius_m",
    )
    @classmethod
    def validate_positive_thresholds(cls, v: float) -> float:
        if v < 0.0:
            raise ValueError(f"Параметр геометрии не может быть отрицательным, получено: {v}")
        return v

    @field_validator("door_gap_max_m")
    @classmethod
    def validate_door_range(cls, v: float, info) -> float:
        min_gap = info.data.get("door_gap_min_m")
        if min_gap is not None and v < min_gap:
            raise ValueError(
                f"door_gap_max_m ({v} м) не может быть меньше door_gap_min_m ({min_gap} м)"
            )
        return v


class ProtectedOpening(BaseModel):
    point_a: Point2D
    point_b: Point2D
    width_m: float


class ConsolidationMetrics(BaseModel):
    raw_count: int
    noise_filtered_count: int
    dedup_count: int
    merge_operations_count: int
    post_merge_count: int
    post_snap_dedup_count: int
    final_count: int
    protected_openings_count: int
    reduction_percent: float


class DryRunResult(BaseModel):
    metrics: ConsolidationMetrics
    protected_openings: List[ProtectedOpening]
    consolidated_segments_cad: List[Segment2D]


@dataclass
class MetricSegment:
    p1: Point2D
    p2: Point2D
    length: float
    vx: float
    vy: float
    angle: float

    @classmethod
    def from_points(cls, p1: Point2D, p2: Point2D) -> "MetricSegment":
        if (p1[0], p1[1]) > (p2[0], p2[1]):
            p1, p2 = p2, p1
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        length = math.hypot(dx, dy)
        if length < 1e-9:
            vx, vy = 1.0, 0.0
            angle = 0.0
        else:
            vx, vy = dx / length, dy / length
            angle = math.atan2(vy, vx) % math.pi
        return cls(p1=p1, p2=p2, length=length, vx=vx, vy=vy, angle=angle)


class WallConsolidator:
    def __init__(self, params: Optional[ConsolidationParams] = None):
        self.params = params or ConsolidationParams()

    def _to_metric(self, seg_cad: Segment2D) -> MetricSegment:
        k = self.params.k
        p1 = (seg_cad[0][0] * k, seg_cad[0][1] * k)
        p2 = (seg_cad[1][0] * k, seg_cad[1][1] * k)
        return MetricSegment.from_points(p1, p2)

    def _to_cad(self, seg_m: MetricSegment) -> Segment2D:
        k = self.params.k
        p1 = (round(seg_m.p1[0] / k, 6), round(seg_m.p1[1] / k, 6))
        p2 = (round(seg_m.p2[0] / k, 6), round(seg_m.p2[1] / k, 6))
        return (p1, p2)

    def filter_noise(self, segments: List[MetricSegment]) -> List[MetricSegment]:
        """Отсекает сегменты с длиной строго меньше min_wall_length_m."""
        threshold = self.params.min_wall_length_m
        return [s for s in segments if s.length >= threshold]

    def deduplicate(
        self, segments: List[MetricSegment], tol_m: float = 0.005
    ) -> List[MetricSegment]:
        """Удаляет нулевые отрезки и дубликаты."""
        unique: List[MetricSegment] = []
        for s in segments:
            if s.length < tol_m:
                continue
            is_dup = False
            for u in unique:
                d11 = math.hypot(s.p1[0] - u.p1[0], s.p1[1] - u.p1[1])
                d22 = math.hypot(s.p2[0] - u.p2[0], s.p2[1] - u.p2[1])
                if d11 <= tol_m and d22 <= tol_m:
                    is_dup = True
                    break
            if not is_dup:
                unique.append(s)
        return unique

    def _is_collinear_and_aligned(
        self, s1: MetricSegment, s2: MetricSegment
    ) -> Tuple[bool, float, float, float, float]:
        """Проверяет коллинеарность и возвращает (успех, p1_min, p1_max, p2_min, p2_max)."""
        angle_diff = abs(s1.angle - s2.angle)
        angle_diff = min(angle_diff, math.pi - angle_diff)
        if angle_diff > math.radians(self.params.angle_tolerance_deg):
            return False, 0.0, 0.0, 0.0, 0.0

        nx, ny = -s1.vy, s1.vx
        v12_x = s2.p1[0] - s1.p1[0]
        v12_y = s2.p1[1] - s1.p1[1]
        lat_dist = abs(v12_x * nx + v12_y * ny)
        if lat_dist > self.params.lateral_offset_m:
            return False, 0.0, 0.0, 0.0, 0.0

        ax, ay = s1.vx, s1.vy

        def proj(p: Point2D) -> float:
            return p[0] * ax + p[1] * ay

        p1_proj = [proj(s1.p1), proj(s1.p2)]
        p2_proj = [proj(s2.p1), proj(s2.p2)]

        return (
            True,
            min(p1_proj),
            max(p1_proj),
            min(p2_proj),
            max(p2_proj),
        )

    def _is_direct_neighbor(
        self,
        s1: MetricSegment,
        s2: MetricSegment,
        pool: List[MetricSegment],
        p1_max: float,
        p2_min: float,
    ) -> bool:
        """Проверяет, что между s1 и s2 вдоль общей оси нет промежуточных сегментов."""
        ax, ay = s1.vx, s1.vy
        nx, ny = -s1.vy, s1.vx

        gap_start = min(p1_max, p2_min)
        gap_end = max(p1_max, p2_min)

        def proj(p: Point2D) -> float:
            return p[0] * ax + p[1] * ay

        for other in pool:
            if other is s1 or other is s2:
                continue

            angle_diff = abs(s1.angle - other.angle)
            angle_diff = min(angle_diff, math.pi - angle_diff)
            if angle_diff > math.radians(self.params.angle_tolerance_deg):
                continue

            v_x = other.p1[0] - s1.p1[0]
            v_y = other.p1[1] - s1.p1[1]
            if abs(v_x * nx + v_y * ny) > self.params.lateral_offset_m:
                continue

            op_min = min(proj(other.p1), proj(other.p2))
            op_max = max(proj(other.p1), proj(other.p2))

            # Если промежуточный отрезок лежит внутри или перекрывает зазор
            if max(gap_start, op_min) < min(gap_end, op_max):
                return False

        return True

    def _check_merge_or_opening(
        self, s1: MetricSegment, s2: MetricSegment, pool: List[MetricSegment]
    ) -> Tuple[bool, Optional[ProtectedOpening]]:
        collinear, p1_min, p1_max, p2_min, p2_max = self._is_collinear_and_aligned(s1, s2)
        if not collinear:
            return False, None

        gap = max(0.0, max(p1_min, p2_min) - min(p1_max, p2_max))

        # Защита дверных проемов 0.6 - 1.5 м
        if self.params.door_gap_min_m <= gap <= self.params.door_gap_max_m:
            if self._is_direct_neighbor(s1, s2, pool, min(p1_max, p2_max), max(p1_min, p2_min)):
                if p1_max < p2_min:
                    pt_a, pt_b = s1.p2, s2.p1
                else:
                    pt_a, pt_b = s2.p2, s1.p1

                opening = ProtectedOpening(
                    point_a=(
                        round(pt_a[0] / self.params.k, 6),
                        round(pt_a[1] / self.params.k, 6),
                    ),
                    point_b=(
                        round(pt_b[0] / self.params.k, 6),
                        round(pt_b[1] / self.params.k, 6),
                    ),
                    width_m=round(gap, 3),
                )
                return False, opening

        # Слияние при микро-зазорах или взаимном перекрытии
        if gap <= self.params.eps_snap_m:
            return True, None

        return False, None

    def _merge_pair(self, s1: MetricSegment, s2: MetricSegment) -> MetricSegment:
        ax, ay = s1.vx, s1.vy
        all_pts = [s1.p1, s1.p2, s2.p1, s2.p2]
        projs = [p[0] * ax + p[1] * ay for p in all_pts]
        min_idx = projs.index(min(projs))
        max_idx = projs.index(max(projs))

        p_min = all_pts[min_idx]
        p_max = all_pts[max_idx]

        proj_val_max = (p_max[0] - s1.p1[0]) * ax + (p_max[1] - s1.p1[1]) * ay
        p2_aligned = (s1.p1[0] + proj_val_max * ax, s1.p1[1] + proj_val_max * ay)

        proj_val_min = (p_min[0] - s1.p1[0]) * ax + (p_min[1] - s1.p1[1]) * ay
        p1_aligned = (s1.p1[0] + proj_val_min * ax, s1.p1[1] + proj_val_min * ay)

        return MetricSegment.from_points(p1_aligned, p2_aligned)

    def _apply_tl_snapping(self, segments: List[MetricSegment]) -> List[MetricSegment]:
        radius = self.params.tl_snap_radius_m
        updated = list(segments)

        for i, s1 in enumerate(updated):
            for pt_attr in ("p1", "p2"):
                pt = getattr(s1, pt_attr)
                for j, s2 in enumerate(updated):
                    if i == j:
                        continue
                    dx = s2.p2[0] - s2.p1[0]
                    dy = s2.p2[1] - s2.p1[1]
                    l2 = dx * dx + dy * dy
                    if l2 < 1e-9:
                        continue
                    t = max(0.0, min(1.0, ((pt[0] - s2.p1[0]) * dx + (pt[1] - s2.p1[1]) * dy) / l2))
                    proj_x = s2.p1[0] + t * dx
                    proj_y = s2.p1[1] + t * dy
                    dist = math.hypot(pt[0] - proj_x, pt[1] - proj_y)

                    if 1e-4 < dist <= radius:
                        new_pt = (proj_x, proj_y)
                        if pt_attr == "p1":
                            updated[i] = MetricSegment.from_points(new_pt, s1.p2)
                        else:
                            updated[i] = MetricSegment.from_points(s1.p1, new_pt)
                        break
        return updated

    def run_dry_run(self, raw_segments_cad: List[Segment2D]) -> DryRunResult:
        raw_count = len(raw_segments_cad)
        metric_pool = [self._to_metric(seg) for seg in raw_segments_cad]

        # 1. Отсечение шума
        filtered_noise = self.filter_noise(metric_pool)
        noise_filtered_count = len(filtered_noise)

        # 2. Первичная дедупликация
        pool = self.deduplicate(filtered_noise)
        dedup_count = len(pool)

        # 3. Коллинеарное слияние с защитой смежных проёмов
        protected_openings: Dict[Tuple[float, float, float, float], ProtectedOpening] = {}
        merge_operations_count = 0
        merged_any = True

        while merged_any:
            merged_any = False
            n = len(pool)
            i = 0
            while i < n:
                j = i + 1
                while j < n:
                    can_merge, opening = self._check_merge_or_opening(pool[i], pool[j], pool)
                    if opening:
                        key = (
                            round(opening.point_a[0], 2),
                            round(opening.point_a[1], 2),
                            round(opening.point_b[0], 2),
                            round(opening.point_b[1], 2),
                        )
                        protected_openings[key] = opening

                    if can_merge:
                        pool[i] = self._merge_pair(pool[i], pool[j])
                        pool.pop(j)
                        n -= 1
                        merge_operations_count += 1
                        merged_any = True
                    else:
                        j += 1
                i += 1

        post_merge_count = len(pool)

        # 4. T/L Snapping
        snapped_pool = self._apply_tl_snapping(pool)

        # 5. Повторная дедупликация после геометрической дотяжки
        final_metric_pool = self.deduplicate(snapped_pool)
        post_snap_dedup_count = len(final_metric_pool)

        # 6. Обратная проекция в CAD-координаты
        cad_segments = [self._to_cad(s) for s in final_metric_pool]
        final_count = len(cad_segments)

        reduction = round((1.0 - final_count / max(1, raw_count)) * 100, 2)

        return DryRunResult(
            metrics=ConsolidationMetrics(
                raw_count=raw_count,
                noise_filtered_count=noise_filtered_count,
                dedup_count=dedup_count,
                merge_operations_count=merge_operations_count,
                post_merge_count=post_merge_count,
                post_snap_dedup_count=post_snap_dedup_count,
                final_count=final_count,
                protected_openings_count=len(protected_openings),
                reduction_percent=reduction,
            ),
            protected_openings=list(protected_openings.values()),
            consolidated_segments_cad=cad_segments,
        )
