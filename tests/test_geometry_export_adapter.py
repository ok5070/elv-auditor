from copy import deepcopy

from app.geometry_export import adapt_room_plan_geometry
from app.services.wall_consolidator import ConsolidationParams


def test_adapt_room_plan_geometry_preserves_contract_and_input():
    payload = {
        "version": 2,
        "canvas": {"width": 2650, "height": 1850},
        "walls": [
            {"id": "w1", "type": "wall", "x1": 0, "y1": 0, "x2": 100, "y2": 0, "thickness": 13},
            {"id": "p1", "type": "partition", "x1": 0, "y1": 100, "x2": 100, "y2": 100, "thickness": 7},
        ],
        "doors": [{"id": "d1"}],
        "windows": [{"id": "win1"}],
    }
    original = deepcopy(payload)

    result = adapt_room_plan_geometry(payload, ConsolidationParams(k=0.1))

    assert payload == original
    assert result["version"] == 2
    assert result["schema_version"] == "2.0"
    assert len(result["walls"]) == 2
    assert {wall["type"] for wall in result["walls"]} == {"wall", "partition"}
    assert result["walls"][0]["x1"] == 0.0
    assert result["walls"][0]["x2"] == 100.0
    assert result["doors"] == payload["doors"]
    assert result["windows"] == payload["windows"]
