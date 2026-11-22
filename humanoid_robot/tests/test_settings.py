import json
import os

from config.settings import Settings, merge_validated


def test_defaults_used_when_no_file(tmp_path):
    s = Settings(str(tmp_path))
    assert s.source == "defaults"
    assert s.get("thresholds", "obstacle_stop_cm") == 25


def test_damaged_main_file_falls_back_to_backup(tmp_path):
    s = Settings(str(tmp_path))
    s.update({"thresholds": {"obstacle_stop_cm": 33}})
    assert s.save()["persisted"] is True
    with open(s.path, "w") as f:
        f.write('{"thresholds": {"obstacle_stop_cm": 4')  # half-written file
    again = Settings(str(tmp_path))
    assert again.source == "backup file"
    assert again.get("thresholds", "obstacle_stop_cm") == 33


def test_both_files_damaged_uses_defaults(tmp_path):
    for name in ("settings.json", "settings.json.bak"):
        (tmp_path / name).write_text("garbage")
    s = Settings(str(tmp_path))
    assert s.source == "defaults"


def test_save_is_refused_in_protected_mode(tmp_path):
    s = Settings(str(tmp_path), is_protected=lambda: True)
    s.update({"thresholds": {"temp_warning_c": 50}})
    result = s.save()
    assert result["persisted"] is False
    assert not os.path.exists(s.path)
    assert s.get("thresholds", "temp_warning_c") == 50  # still applied in RAM


def test_save_leaves_no_temp_file(tmp_path):
    s = Settings(str(tmp_path))
    s.save()
    assert sorted(os.listdir(tmp_path)) == ["settings.json", "settings.json.bak"]
    json.loads((tmp_path / "settings.json").read_text())


def test_wrong_types_and_ranges_are_rejected(tmp_path):
    (tmp_path / "settings.json").write_text(json.dumps({
        "servos": {"R_HIP": {"trim": 99, "min": 170, "max": 20, "invert": "yes", "channel": 0.0}},
        "thresholds": {"obstacle_stop_cm": "near"},
    }))
    s = Settings(str(tmp_path))
    hip = s.get("servos", "R_HIP")
    assert hip["trim"] == 30            # clamped
    assert hip["min"] < hip["max"]      # swapped
    assert hip["invert"] is False       # wrong type -> default
    assert s.get("thresholds", "obstacle_stop_cm") == 25


def test_duplicate_channels_restore_default_table(tmp_path):
    (tmp_path / "settings.json").write_text(json.dumps({"servos": {"R_HIP": {"channel": 1}}}))
    s = Settings(str(tmp_path))
    assert s.get("servos", "R_HIP")["channel"] == 0


def test_merge_ignores_unknown_keys():
    assert merge_validated({"a": 1}, {"a": 2, "b": 3}) == {"a": 2}
