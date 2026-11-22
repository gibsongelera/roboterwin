"""MCP3008 analog inputs (MQ-2 gas sensor and battery voltage) and gas logic.

The MCP3008 is powered from 3.3 V, so every input must stay below 3.3 V:
  CH0  MQ-2 AO (0-5 V)  -> 10k / 20k divider  -> max 3.33 V   (ratio 1.5)
  CH1  battery (16.8 V) -> 100k / 22k divider -> max 3.03 V   (ratio 5.545)
"""


class MCP3008:
    def __init__(self, bus=0, device=0, vref=3.3, speed_hz=1_000_000):
        import spidev
        self.vref = vref
        self._spi = spidev.SpiDev()
        self._spi.open(bus, device)
        self._spi.max_speed_hz = speed_hz
        self._spi.mode = 0

    def read_raw(self, channel):
        reply = self._spi.xfer2([1, (8 + channel) << 4, 0])
        return ((reply[1] & 0x03) << 8) | reply[2]

    def read_voltage(self, channel, samples=5):
        total = sum(self.read_raw(channel) for _ in range(samples))
        return total / samples * self.vref / 1023.0

    def close(self):
        self._spi.close()


class GasMonitor:
    """Turns the MQ-2 voltage into a level: warmup / normal / warning / danger / absent.

    The MQ-2 heater needs time after power-on, and its clean-air voltage differs
    between sensors and rooms. So the monitor learns a *baseline* at the end of
    warm-up and alarms on a sudden *rise* above it. The baseline follows slow
    drift downwards quickly and upwards only very slowly, so slowly building
    smoke cannot "teach" the robot that smoke is normal. An absolute limit
    (danger_absolute_v) still raises the alarm if the robot was switched on
    in a smoky room and learned a bad baseline.

    This is a prototype indicator, NOT a certified smoke or gas alarm.
    """

    ABSENT_BELOW_V = 0.03   # with the divider, a disconnected AO pin reads ~0 V

    def __init__(self, warmup_s, warning_rise_v, danger_rise_v, danger_absolute_v):
        self.configure(warmup_s, warning_rise_v, danger_rise_v, danger_absolute_v)
        self.started = None
        self.baseline = None
        self._samples = []
        self.level = "warmup"

    def configure(self, warmup_s, warning_rise_v, danger_rise_v, danger_absolute_v):
        self.warmup_s = warmup_s
        self.warning_rise = warning_rise_v
        self.danger_rise = danger_rise_v
        self.danger_absolute = danger_absolute_v

    def warmup_left(self, now):
        if self.started is None:
            return self.warmup_s
        return max(0.0, self.warmup_s - (now - self.started))

    def update(self, sensor_v, now):
        if sensor_v is None:
            self.level = "error"
            return self.level
        if self.started is None:
            self.started = now
        if sensor_v < self.ABSENT_BELOW_V:
            self.level = "absent"
            return self.level
        if self.baseline is None:
            if now - self.started < self.warmup_s:
                self._samples = (self._samples + [sensor_v])[-50:]
                self.level = "warmup"
                return self.level
            recent = self._samples[-20:] or [sensor_v]
            self.baseline = sum(recent) / len(recent)
        rise = sensor_v - self.baseline
        if rise >= self.danger_rise or sensor_v >= self.danger_absolute:
            self.level = "danger"
        elif rise >= self.warning_rise:
            self.level = "warning"
        else:
            self.level = "normal"
            alpha = 0.05 if rise < 0 else 0.0005
            self.baseline += alpha * rise
        return self.level
