import json

import pytest

from aggregate_site_results import aggregate


def _summary(window=(0, 8)):
    return {
        "session_role": "confirmation",
        "parameters_frozen": True,
        "protocol_version": "test-v1",
        "site_id": "house-a",
        "pcb_design_id": "pcb-v1",
        "device_id": "device-a",
        "container_id": "box-a",
        "index_weights": {"NH3": 0.3, "H2S": 0.35, "CH4": 0.1, "BME": 0.25},
        "index_interpretation": "engineered change",
        "time_to_sustained_change_h": 2.0,
        "primary_event_detected": True,
        "auc_window_h": list(window),
        "auc_valid": True,
        "auc_change_index_hours": 200.0,
        "index_at_fixed_hours": {"8": 80.0},
    }


def test_aggregate_labels_auc_from_recorded_window(tmp_path):
    path = tmp_path / "summary.json"
    path.write_text(json.dumps(_summary()), encoding="utf-8")

    result = aggregate([path])

    assert result["auc_window_h"] == [0.0, 8.0]
    assert result["overall"]["auc_0_8h"]["mean"] == 200.0
    assert "auc_0_4h" not in result["overall"]


def test_aggregate_rejects_mixed_auc_windows(tmp_path):
    paths = []
    for number, window in enumerate(((0, 8), (0, 4))):
        path = tmp_path / f"summary_{number}.json"
        path.write_text(json.dumps(_summary(window)), encoding="utf-8")
        paths.append(path)

    with pytest.raises(ValueError, match="one recorded AUC window"):
        aggregate(paths)
