import ezdxf

from app.geometry_export import build_geometry_export


def test_generic_plan_uses_heavy_lines_only_and_keeps_openings_empty():
    document = ezdxf.new()
    document.layers.new("План")
    modelspace = document.modelspace()
    modelspace.add_line((0, 0), (10, 0), dxfattribs={"layer": "План", "lineweight": 30})
    modelspace.add_line((0, 5), (10, 5), dxfattribs={"layer": "План", "lineweight": 18})

    result = build_geometry_export(document, "plan.dxf", k=0.1)

    assert len(result["walls"]) == 1
    assert result["walls"][0]["confidence"] == "generic_plan_lineweight"
    assert result["doors"] == []
    assert result["windows"] == []
    assert result["metadata"]["wall_detection"]["raw_candidates"] == 1


def test_english_generic_plan_layer_is_supported():
    document = ezdxf.new()
    document.layers.new("PLAN")
    document.modelspace().add_line(
        (0, 0), (10, 0), dxfattribs={"layer": "PLAN", "lineweight": 30}
    )

    result = build_geometry_export(document, "plan.dxf", k=0.1)

    assert len(result["walls"]) == 1


def test_explicit_partition_layer_is_classified_and_consolidated():
    document = ezdxf.new()
    document.layers.new("АР_ПЕРЕГОРОДКИ")
    modelspace = document.modelspace()
    modelspace.add_line((0, 0), (5, 0), dxfattribs={"layer": "АР_ПЕРЕГОРОДКИ"})
    modelspace.add_line((5.2, 0), (10, 0), dxfattribs={"layer": "АР_ПЕРЕГОРОДКИ"})

    result = build_geometry_export(document, "partition.dxf", k=0.1)

    assert len(result["walls"]) == 1
    assert result["walls"][0]["type"] == "partition"
    assert result["walls"][0]["thickness"] == 7.0
    assert result["metadata"]["wall_detection"]["merge_operations"] == 1
