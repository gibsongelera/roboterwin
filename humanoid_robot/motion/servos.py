"""Servo joints: home position, trim, direction, safe limits and speed limit.

Motion code works in *offsets* (degrees away from the home pose) using one
convention for both sides of the body (see docs/BUILD_GUIDE.md, "Servo
directions"). Each joint converts an offset to a real servo angle:

    angle = clamp(home + trim + (-offset if invert else offset), min, max)

so a mirrored servo on the left leg only needs ``invert: true``.
"""

import threading


def _clamp(value, low, high):
    return max(low, min(high, value))


class Joint:
    def __init__(self, name, cfg, type_cfg):
        self.name = name
        self.configure(cfg, type_cfg)

    def configure(self, cfg, type_cfg):
        self.channel = int(cfg["channel"])
        self.type = cfg["type"]
        self.home = float(cfg["home"])
        self.min = float(cfg["min"])
        self.max = float(cfg["max"])
        self.invert = bool(cfg["invert"])
        self.trim = float(cfg["trim"])
        self.min_us = float(type_cfg["min_us"])
        self.max_us = float(type_cfg["max_us"])
        self.range_deg = float(type_cfg["range_deg"])

    def servo_angle(self, offset):
        direction = -1.0 if self.invert else 1.0
        return _clamp(self.home + self.trim + direction * offset, self.min, self.max)

    def pulse_us(self, angle):
        return self.min_us + (self.max_us - self.min_us) * angle / self.range_deg


class ServoController:
    """Owns the PCA9685 and its output-enable line.

    ``write`` is called by the motion thread only; ``configure`` may be called
    from the web thread (live trim changes), so both take the lock.
    """

    def __init__(self, pwm, enable_line, servos_cfg, types_cfg, max_speed_deg_per_s):
        self._lock = threading.Lock()
        self.pwm = pwm
        self.enable_line = enable_line
        self.joints = {name: Joint(name, cfg, types_cfg[cfg["type"]]) for name, cfg in servos_cfg.items()}
        self.current = {name: 0.0 for name in self.joints}
        self.max_speed = float(max_speed_deg_per_s)
        self.enabled = False

    @property
    def available(self):
        return self.pwm is not None

    def configure(self, servos_cfg, types_cfg, max_speed_deg_per_s):
        with self._lock:
            for name, cfg in servos_cfg.items():
                if name in self.joints:
                    self.joints[name].configure(cfg, types_cfg[cfg["type"]])
            self.max_speed = float(max_speed_deg_per_s)
            if self.enabled:
                self._output(self.current)

    def enable(self):
        """Load the home pose into the PCA9685, then switch the outputs on."""
        if not self.available:
            return False
        with self._lock:
            self.current = {name: 0.0 for name in self.joints}
            self._output(self.current)
            if self.enable_line is not None:
                self.enable_line.on()
            self.enabled = True
        return True

    def disable(self):
        """Stop all servo signals (servos go limp)."""
        with self._lock:
            if self.enable_line is not None:
                self.enable_line.off()
            if self.pwm is not None:
                self.pwm.all_off()
            self.enabled = False

    def write(self, targets, dt):
        """Move toward ``targets`` (offsets) no faster than the speed limit."""
        if not self.enabled:
            return
        with self._lock:
            max_step = self.max_speed * dt
            for name, target in targets.items():
                if name not in self.current:
                    continue
                delta = _clamp(target - self.current[name], -max_step, max_step)
                self.current[name] += delta
            self._output(self.current)

    def _output(self, offsets):
        for name, offset in offsets.items():
            joint = self.joints[name]
            self.pwm.set_pulse_us(joint.channel, joint.pulse_us(joint.servo_angle(offset)))

    def angles(self):
        with self._lock:
            return {name: round(self.joints[name].servo_angle(off), 1) for name, off in self.current.items()}
