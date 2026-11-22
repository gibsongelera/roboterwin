"""Robot settings: built-in defaults + the robot's saved settings file.

SD card safety rules implemented here:
* Loading never fails. Order: saved file -> backup copy -> built-in defaults.
  Every value is type-checked and range-checked, so a damaged or hand-edited
  file can never produce a dangerous servo command or stop the robot booting.
* Saving is atomic (temp file + fsync + rename + directory fsync). A power cut
  during a save leaves either the old or the new file, never a half-written one.
* In protected (read-only) mode nothing is written to the SD card. Changes stay
  in RAM until the next reboot; the web page tells the user this.
"""

import copy
import json
import logging
import math
import os
import threading

log = logging.getLogger(__name__)

CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULTS_PATH = os.path.join(CODE_DIR, "config", "defaults.json")
SETTINGS_NAME = "settings.json"

_SERVO_RANGES = {"home": (0, 180), "min": (0, 180), "max": (0, 180), "trim": (-30, 30)}
_MAX_STRING = 500


def merge_validated(default, user):
    """Return a copy of ``default`` with values from ``user`` where the type matches.

    Unknown keys in ``user`` are ignored, wrong types fall back to the default.
    """
    if isinstance(default, dict):
        user = user if isinstance(user, dict) else {}
        return {k: (merge_validated(v, user[k]) if k in user else copy.deepcopy(v))
                for k, v in default.items()}
    if isinstance(default, bool):
        return user if isinstance(user, bool) else default
    if isinstance(default, (int, float)):
        if isinstance(user, (int, float)) and not isinstance(user, bool) and math.isfinite(user):
            return user
        return default
    if isinstance(default, str):
        return user if isinstance(user, str) and len(user) <= _MAX_STRING else default
    if isinstance(default, list):
        return copy.deepcopy(user) if isinstance(user, list) else copy.deepcopy(default)
    return copy.deepcopy(default)


def _clamp(value, low, high):
    return max(low, min(high, value))


def sanitize(data, defaults):
    """Range-check values that could be dangerous if wrong. Modifies ``data`` in place."""
    types = data.get("servo_types", {})
    for name, joint in data.get("servos", {}).items():
        default_joint = defaults["servos"].get(name, {})
        for key, (low, high) in _SERVO_RANGES.items():
            joint[key] = _clamp(joint[key], low, high)
        joint["channel"] = int(_clamp(int(joint["channel"]), 0, 15))
        if joint["min"] > joint["max"]:
            joint["min"], joint["max"] = joint["max"], joint["min"]
        joint["home"] = _clamp(joint["home"], joint["min"], joint["max"])
        if joint["type"] not in types:
            joint["type"] = default_joint.get("type", next(iter(types)))
    channels = [j["channel"] for j in data.get("servos", {}).values()]
    if len(channels) != len(set(channels)):
        log.error("Duplicate servo channels in settings; using default servo table")
        data["servos"] = copy.deepcopy(defaults["servos"])
    t = data["thresholds"]
    t["obstacle_stop_cm"] = _clamp(t["obstacle_stop_cm"], 5, 150)
    t["obstacle_clear_cm"] = max(t["obstacle_clear_cm"], t["obstacle_stop_cm"] + 5)
    t["temp_danger_c"] = max(t["temp_danger_c"], t["temp_warning_c"])
    t["gas_danger_rise_v"] = max(t["gas_danger_rise_v"], t["gas_warning_rise_v"])
    t["gas_danger_absolute_v"] = _clamp(t["gas_danger_absolute_v"], 0.5, 5.0)
    t["battery_warning_v"] = max(t["battery_warning_v"], t["battery_shutdown_v"])
    m = data["motion"]
    m["watchdog_ms"] = _clamp(m["watchdog_ms"], 200, 2000)
    m["step_ms"] = _clamp(m["step_ms"], 120, 2000)
    m["max_speed_deg_per_s"] = _clamp(m["max_speed_deg_per_s"], 30, 600)
    return data


def _write_fsync(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())


def _fsync_dir(directory):
    # Makes the rename itself durable. Not supported on Windows (sim mode).
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def atomic_write_json(path, data):
    """Write ``data`` as JSON so that ``path`` is always either old or new, never partial."""
    tmp = path + ".tmp"
    _write_fsync(tmp, json.dumps(data, indent=2, sort_keys=True))
    os.replace(tmp, path)
    _fsync_dir(os.path.dirname(path) or ".")


def read_json(path):
    """Return parsed JSON from ``path`` or None if missing/damaged."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            value = json.load(f)
        return value if isinstance(value, dict) else None
    except (OSError, ValueError) as exc:
        if os.path.exists(path):
            log.warning("Ignoring damaged settings file %s: %s", path, exc)
        return None


class Settings:
    """Thread-safe settings store."""

    def __init__(self, data_dir, defaults_path=DEFAULTS_PATH, is_protected=None):
        self._lock = threading.RLock()
        self.data_dir = data_dir
        self.path = os.path.join(data_dir, SETTINGS_NAME)
        self.backup_path = self.path + ".bak"
        self.is_protected = is_protected or (lambda: False)
        with open(defaults_path, "r", encoding="utf-8") as f:
            self.defaults = json.load(f)
        self.source = "defaults"
        self.data = self._load()

    def _load(self):
        for path, label in ((self.path, "saved file"), (self.backup_path, "backup file")):
            user = read_json(path)
            if user is not None:
                self.source = label
                log.info("Settings loaded from %s", path)
                return sanitize(merge_validated(self.defaults, user), self.defaults)
        self.source = "defaults"
        log.info("Using built-in default settings")
        return sanitize(copy.deepcopy(self.defaults), self.defaults)

    def section(self, name):
        with self._lock:
            return copy.deepcopy(self.data[name])

    def get(self, section, key):
        with self._lock:
            return copy.deepcopy(self.data[section][key])

    def snapshot(self):
        with self._lock:
            return copy.deepcopy(self.data)

    def update(self, patch):
        """Apply a partial update (validated). Returns the new full settings."""
        with self._lock:
            merged = copy.deepcopy(self.data)
            _deep_update(merged, patch if isinstance(patch, dict) else {})
            self.data = sanitize(merge_validated(self.data, merged), self.defaults)
            return copy.deepcopy(self.data)

    def save(self):
        """Persist settings. Returns {"persisted": bool, "message": str}."""
        if self.is_protected():
            return {"persisted": False,
                    "message": "Protected mode: saved for this session only. "
                               "Switch to Maintenance mode to save permanently."}
        with self._lock:
            data = copy.deepcopy(self.data)
        try:
            os.makedirs(self.data_dir, exist_ok=True)
            atomic_write_json(self.path, data)
            atomic_write_json(self.backup_path, data)
        except OSError as exc:
            log.error("Saving settings failed: %s", exc)
            return {"persisted": False, "message": "Saving failed: %s" % exc}
        self.source = "saved file"
        return {"persisted": True, "message": "Settings saved permanently."}


def _deep_update(target, patch):
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = value
