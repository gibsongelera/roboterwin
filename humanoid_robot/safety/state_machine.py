"""Safety rules: decides the robot state and which motion is allowed.

Priority (highest first):
  1. STOPPED    emergency stop latched (button or phone) -> hold pose, no motion
  2. EMERGENCY  smoke/gas or heat danger -> stop walking, alarm.
                After the operator presses "Silence / acknowledge" on the phone,
                manual driving is allowed again (to move the robot away).
  3. OBSTACLE   something closer than obstacle_stop_cm -> forward is blocked
                (backward and turning still allowed; auto mode turns away)
  4. WARNING    temperature / gas / battery warning -> motion allowed, yellow LED
  5. MOVING / READY

Manual commands expire after motion.watchdog_ms: if the phone stops sending
(Wi-Fi lost, browser closed, phone locked) the robot stops by itself.
"""

import math
from dataclasses import dataclass, field
from typing import List, Optional

MODES = ("monitor", "manual", "auto")
DEADZONE = 0.2


@dataclass
class Inputs:
    distance_cm: Optional[float] = None
    temp_c: Optional[float] = None
    gas_level: str = "warmup"         # warmup / normal / warning / danger / absent / error
    battery_level: str = "absent"     # absent / ok / low / critical


@dataclass
class Hazard:
    level: str     # "warning" or "danger"
    key: str
    text: str


@dataclass
class Decision:
    state: str
    motion: str                       # stop / forward / backward / left / right / freeze
    speed: float = 0.0
    hazards: List[Hazard] = field(default_factory=list)
    blocked: bool = False
    note: str = ""


def classify_drive(x, y):
    """Joystick (x right+, y forward+) -> (motion, speed 0.3..1)."""
    magnitude = min(1.0, math.hypot(x, y))
    if magnitude < DEADZONE:
        return "stop", 0.0
    speed = 0.3 + 0.7 * (magnitude - DEADZONE) / (1.0 - DEADZONE)
    if abs(y) >= abs(x):
        return ("forward" if y > 0 else "backward"), speed
    return ("right" if x > 0 else "left"), speed


class SafetyController:
    def __init__(self, thresholds, motion_cfg):
        self.mode = "monitor"
        self.estopped = False
        self._drive = (0.0, 0.0)
        self._drive_time = None
        self._auto_turning = False
        self._silence_until = 0.0
        self.configure(thresholds, motion_cfg)

    def configure(self, thresholds, motion_cfg):
        self.t = dict(thresholds)
        self.watchdog_s = motion_cfg["watchdog_ms"] / 1000.0
        self.auto_speed = float(motion_cfg["auto_speed"])

    # ----- commands --------------------------------------------------------
    def set_mode(self, mode):
        if mode not in MODES:
            return False
        self.mode = mode
        self._drive_time = None
        self._auto_turning = False
        return True

    def drive(self, x, y, now):
        """Manual joystick command. Phone control always takes priority."""
        self.mode = "manual"
        self._drive = (max(-1.0, min(1.0, float(x))), max(-1.0, min(1.0, float(y))))
        self._drive_time = now

    def stop_drive(self):
        self._drive_time = None

    def estop(self):
        self.estopped = True
        self._drive_time = None

    def reset_estop(self):
        self.estopped = False
        self._drive_time = None

    def silence(self, now):
        self._silence_until = now + float(self.t["silence_s"])

    def silenced(self, now):
        return now < self._silence_until

    def silence_left(self, now):
        return max(0.0, self._silence_until - now)

    # ----- evaluation ------------------------------------------------------
    def hazards(self, inputs):
        found = []
        t = self.t
        if inputs.temp_c is not None:
            if inputs.temp_c >= t["temp_danger_c"]:
                found.append(Hazard("danger", "heat", "High temperature detected, %d degrees" % round(inputs.temp_c)))
            elif inputs.temp_c >= t["temp_warning_c"]:
                found.append(Hazard("warning", "heat", "Temperature is high, %d degrees" % round(inputs.temp_c)))
        if inputs.gas_level == "danger":
            found.append(Hazard("danger", "gas", "Smoke or gas detected"))
        elif inputs.gas_level == "warning":
            found.append(Hazard("warning", "gas", "Possible smoke or gas detected"))
        if inputs.battery_level == "critical":
            found.append(Hazard("warning", "battery_critical", "Battery critical"))
        elif inputs.battery_level == "low":
            found.append(Hazard("warning", "battery", "Battery is low"))
        return found

    def _desired(self, inputs, now):
        if self.mode == "manual":
            if self._drive_time is not None and now - self._drive_time <= self.watchdog_s:
                return classify_drive(*self._drive)
            return "stop", 0.0
        if self.mode == "auto":
            if self._auto_turning:
                if inputs.distance_cm is not None and inputs.distance_cm >= self.t["obstacle_clear_cm"]:
                    self._auto_turning = False
                else:
                    return "left", self.auto_speed
            return "forward", self.auto_speed
        return "stop", 0.0

    def update(self, inputs, now):
        hazards = self.hazards(inputs)
        danger = any(h.level == "danger" for h in hazards)
        warning = any(h.level == "warning" for h in hazards)

        if self.estopped:
            return Decision("STOPPED", "freeze", 0.0, hazards, note="Emergency stop is on")

        motion, speed = self._desired(inputs, now)
        if danger and not (self.mode == "manual" and self.silenced(now)):
            return Decision("EMERGENCY", "stop", 0.0, hazards)

        blocked = self._auto_turning
        note = "Turning away from obstacle" if blocked else ""
        if motion == "forward":
            distance = inputs.distance_cm
            if distance is None:
                if self.mode == "auto":
                    motion, speed, blocked = "stop", 0.0, True
                    note = "Distance sensor not working: auto patrol paused"
                else:
                    note = "Distance sensor not working: drive carefully"
            elif distance <= self.t["obstacle_stop_cm"]:
                blocked = True
                if self.mode == "auto":
                    self._auto_turning = True
                    motion = "left"
                    note = "Turning away from obstacle"
                else:
                    motion, speed = "stop", 0.0
                    note = "Obstacle ahead: forward blocked"

        if danger:
            state = "EMERGENCY"
        elif blocked:
            state = "OBSTACLE"
        elif warning:
            state = "WARNING"
        elif motion != "stop":
            state = "MOVING"
        else:
            state = "READY"
        return Decision(state, motion, speed, hazards, blocked, note)
