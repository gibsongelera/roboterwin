"""Raspberry Pi health: SD-card protection mode, power supply and CPU temperature.

Under-voltage is the most common cause of SD card corruption and random
crashes, so it is shown on the web page and announced by voice.
"""

import os
import subprocess

THROTTLED_SYSFS = "/sys/devices/platform/soc/soc:firmware/get_throttled"
CPU_TEMP = "/sys/class/thermal/thermal_zone0/temp"
CMDLINE_FILES = ("/boot/firmware/cmdline.txt", "/boot/cmdline.txt")


def _read(path):
    try:
        with open(path, "r") as f:
            return f.read().strip()
    except OSError:
        return None


def read_throttled():
    """Raw get_throttled bit field, or None if unknown."""
    text = _read(THROTTLED_SYSFS)
    if text:
        try:
            return int(text, 16)
        except ValueError:
            pass
    try:
        out = subprocess.run(["vcgencmd", "get_throttled"], capture_output=True, text=True, timeout=2).stdout
        return int(out.strip().split("=")[1], 16)
    except (OSError, IndexError, ValueError, subprocess.SubprocessError):
        return None


def decode_throttled(value):
    if value is None:
        return {"known": False, "undervoltage_now": False, "undervoltage_seen": False,
                "throttled_now": False, "throttled_seen": False}
    return {
        "known": True,
        "undervoltage_now": bool(value & 0x1),
        "throttled_now": bool(value & 0x4) or bool(value & 0x2),
        "undervoltage_seen": bool(value & 0x10000),
        "throttled_seen": bool(value & 0x40000) or bool(value & 0x20000),
    }


def cpu_temp_c():
    text = _read(CPU_TEMP)
    try:
        return round(int(text) / 1000.0, 1)
    except (TypeError, ValueError):
        return None


def is_protected():
    """True if the SD card overlay (read-only root) is active right now."""
    return "boot=overlay" in (_read("/proc/cmdline") or "")


def protected_after_reboot():
    for path in CMDLINE_FILES:
        text = _read(path)
        if text is not None:
            return "boot=overlay" in text
    return None


def boot_partition_readonly():
    try:
        with open("/proc/mounts", "r") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 4 and parts[1] in ("/boot/firmware", "/boot"):
                    return "ro" in parts[3].split(",")
    except OSError:
        pass
    return None


class SystemHealth:
    def __init__(self, world=None):
        self.world = world  # SimWorld in simulator mode

    def protected(self):
        if self.world is not None:
            return bool(self.world.get("protected"))
        return is_protected()

    def read(self):
        if self.world is not None:
            uv = bool(self.world.get("undervoltage"))
            prot = bool(self.world.get("protected"))
            return {"cpu_temp_c": 45.0, "protected": prot, "protected_after_reboot": prot,
                    "boot_readonly": prot, "known": True, "undervoltage_now": uv,
                    "undervoltage_seen": uv, "throttled_now": False, "throttled_seen": False}
        info = decode_throttled(read_throttled())
        info.update({
            "cpu_temp_c": cpu_temp_c(),
            "protected": is_protected(),
            "protected_after_reboot": protected_after_reboot(),
            "boot_readonly": boot_partition_readonly(),
        })
        return info


def load_average():
    try:
        return round(os.getloadavg()[0], 2)
    except (AttributeError, OSError):
        return None
