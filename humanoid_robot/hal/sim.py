"""Simulated hardware so the whole robot program runs on a normal PC.

Start with:  ROBOT_SIM=1 python main.py   (or  python main.py --sim)
The web page then shows a "Simulator" card to change distance, temperature,
gas, battery and protected mode, so every alarm and safety rule can be tested
without wiring anything.
"""

import threading


class SimWorld:
    """Values the fake sensors report. Changed from the web simulator card."""

    FIELDS = {
        "distance_cm": 120.0,     # < 0 means "sensor not responding"
        "temp_c": 24.0,
        "humidity": 50.0,
        "gas_sensor_v": 0.6,      # MQ-2 AO voltage (before the divider)
        "battery_v": 15.6,
        "protected": False,       # pretend the SD card overlay is active
        "undervoltage": False,
    }

    def __init__(self):
        self._lock = threading.Lock()
        self._values = dict(self.FIELDS)

    def get(self, key):
        with self._lock:
            return self._values[key]

    def to_dict(self):
        with self._lock:
            return dict(self._values)

    def update(self, patch):
        with self._lock:
            for key, value in patch.items():
                if key not in self._values:
                    continue
                default = self.FIELDS[key]
                if isinstance(default, bool):
                    self._values[key] = bool(value)
                elif isinstance(value, (int, float)) and not isinstance(value, bool):
                    self._values[key] = float(value)
            return dict(self._values)


class SimPWM:
    def __init__(self):
        self.pulses = {}
        self.period_us = 20000.0

    def set_pulse_us(self, channel, pulse_us):
        self.pulses[channel] = pulse_us

    def channel_off(self, channel):
        self.pulses.pop(channel, None)

    def all_off(self):
        self.pulses.clear()

    def close(self):
        self.all_off()


class SimOutput:
    """Same small API as gpiozero LED / Buzzer / DigitalOutputDevice."""

    def __init__(self, name=""):
        self.name = name
        self.value = 0

    def on(self):
        self.value = 1

    def off(self):
        self.value = 0

    def close(self):
        self.value = 0


class SimButton:
    """Same callback API as gpiozero Button."""

    def __init__(self, name=""):
        self.name = name
        self.when_pressed = None
        self.when_held = None
        self.when_released = None
        self.is_pressed = False

    def press(self):
        self.is_pressed = True
        if self.when_pressed:
            self.when_pressed()

    def hold(self):
        if self.when_held:
            self.when_held()

    def release(self):
        self.is_pressed = False
        if self.when_released:
            self.when_released()

    def close(self):
        pass


class SimUltrasonic:
    def __init__(self, world):
        self.world = world

    def read_cm(self):
        value = self.world.get("distance_cm")
        return None if value < 0 else float(value)

    def close(self):
        pass


class SimDHT:
    def __init__(self, world):
        self.world = world

    def read(self):
        return self.world.get("temp_c"), self.world.get("humidity")


class SimADC:
    """Returns the voltage at the MCP3008 pin, i.e. after the resistor dividers."""

    def __init__(self, world, calibration, mq2_channel, battery_channel):
        self.world = world
        self.cal = calibration
        self.mq2_channel = mq2_channel
        self.battery_channel = battery_channel

    def read_voltage(self, channel):
        if channel == self.mq2_channel:
            value = self.world.get("gas_sensor_v") / self.cal["mq2_divider_ratio"]
        elif channel == self.battery_channel:
            value = self.world.get("battery_v") / self.cal["battery_divider_ratio"]
        else:
            value = 0.0
        return max(0.0, min(self.cal["adc_vref"], value))

    def close(self):
        pass
