"""4S Li-ion battery monitoring and safe low-battery shutdown.

A Raspberry Pi that browns out while writing can corrupt its SD card, and an
over-discharged Li-ion pack is damaged. So the robot warns at
battery_warning_v and shuts down cleanly when the voltage stays below
battery_shutdown_v for battery_shutdown_delay_s (the delay ignores short dips
while servos draw high current).

Below 6 V the battery is treated as "not connected" (e.g. bench testing with
a USB power supply), and no shutdown happens.
"""

ABSENT_BELOW_V = 6.0
HYSTERESIS_V = 0.2
CELLS = 4
# (volts per cell under light load, percent) - rough Li-ion curve
_CURVE = [(3.30, 0), (3.50, 10), (3.60, 25), (3.70, 45), (3.80, 60),
          (3.90, 73), (4.00, 85), (4.10, 94), (4.20, 100)]


def percent(voltage):
    if voltage is None or voltage < ABSENT_BELOW_V:
        return None
    cell = voltage / CELLS
    if cell <= _CURVE[0][0]:
        return 0
    for (v1, p1), (v2, p2) in zip(_CURVE, _CURVE[1:]):
        if cell <= v2:
            return int(round(p1 + (p2 - p1) * (cell - v1) / (v2 - v1)))
    return 100


class BatteryMonitor:
    def __init__(self, warning_v, shutdown_v, delay_s):
        self.configure(warning_v, shutdown_v, delay_s)
        self.level = "absent"
        self._critical_since = None

    def configure(self, warning_v, shutdown_v, delay_s):
        self.warning_v = warning_v
        self.shutdown_v = shutdown_v
        self.delay_s = delay_s

    def update(self, voltage, now):
        """Return (level, shutdown_due). level: absent / ok / low / critical."""
        if voltage is None or voltage < ABSENT_BELOW_V:
            self.level, self._critical_since = "absent", None
            return self.level, False
        was = self.level
        if voltage <= self.shutdown_v or (was == "critical" and voltage <= self.shutdown_v + HYSTERESIS_V):
            if self._critical_since is None:
                self._critical_since = now
            self.level = "critical"
            return self.level, now - self._critical_since >= self.delay_s
        self._critical_since = None
        if voltage <= self.warning_v or (was in ("low", "critical") and voltage <= self.warning_v + HYSTERESIS_V):
            self.level = "low"
        else:
            self.level = "ok"
        return self.level, False

    def seconds_to_shutdown(self, now):
        if self._critical_since is None:
            return None
        return max(0.0, self.delay_s - (now - self._critical_since))
