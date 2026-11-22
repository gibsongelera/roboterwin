"""HC-SR04 ultrasonic distance sensor.

Uses lgpio edge timestamps (taken by the kernel, so Python timing jitter does
not matter). Unlike a simple library reading it can tell the difference
between "nothing in range" and "sensor not connected":

* no echo pulse starts      -> None (sensor fault, reported on the web page)
* echo longer than max range -> max range (path is clear)

ECHO is a 5 V signal: it MUST go through the 1k/2k divider (docs/WIRING.md).
"""

import threading
import time

SPEED_OF_SOUND_CM_PER_S = 34300.0


class Ultrasonic:
    def __init__(self, trigger, echo, max_cm=250.0, chip=0):
        import lgpio
        self._lg = lgpio
        self.trigger = trigger
        self.echo = echo
        self.max_cm = max_cm
        self._handle = lgpio.gpiochip_open(chip)
        lgpio.gpio_claim_output(self._handle, trigger, 0)
        lgpio.gpio_claim_alert(self._handle, echo, lgpio.BOTH_EDGES)
        self._rise = None
        self._fall = None
        self._edge = threading.Event()
        self._callback = lgpio.callback(self._handle, echo, lgpio.BOTH_EDGES, self._on_edge)

    def _on_edge(self, _chip, _gpio, level, timestamp_ns):
        if level == 1:
            self._rise, self._fall = timestamp_ns, None
        elif level == 0 and self._rise is not None:
            self._fall = timestamp_ns
            self._edge.set()

    def read_cm(self):
        """One measurement in cm, or None if the sensor did not answer."""
        self._rise = self._fall = None
        self._edge.clear()
        self._lg.gpio_write(self._handle, self.trigger, 1)
        time.sleep(0.00002)
        self._lg.gpio_write(self._handle, self.trigger, 0)
        # Echo starts ~0.5 ms after the trigger and lasts at most ~38 ms.
        self._edge.wait(0.06)
        if self._rise is None:
            return None
        if self._fall is None:
            return self.max_cm
        pulse_s = (self._fall - self._rise) / 1e9
        return round(min(self.max_cm, pulse_s * SPEED_OF_SOUND_CM_PER_S / 2.0), 1)

    def close(self):
        try:
            self._callback.cancel()
            self._lg.gpio_free(self._handle, self.echo)
            self._lg.gpio_free(self._handle, self.trigger)
        finally:
            self._lg.gpiochip_close(self._handle)


def median(values):
    ordered = sorted(values)
    return ordered[len(ordered) // 2]
