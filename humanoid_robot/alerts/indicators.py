"""Status LEDs and buzzer patterns.

  STARTING   green -> yellow -> red chase
  READY      green on
  MOVING     green blinking
  OBSTACLE   yellow fast blink
  WARNING    yellow on, short chirp every 5 s
  EMERGENCY  red blinking + buzzer beeping
  STOPPED    red on (emergency stop latched)
  SHUTDOWN   yellow slow blink
"""

import threading
import time


def pattern(state, t, silenced=False):
    """Return (green, yellow, red, buzzer) for a state at time t (seconds)."""
    def blink(hz):
        return (t * hz) % 1.0 < 0.5

    green = yellow = red = buzz = False
    if state == "STARTING":
        phase = int(t * 4) % 3
        green, yellow, red = phase == 0, phase == 1, phase == 2
    elif state == "READY":
        green = True
    elif state == "MOVING":
        green = blink(2)
    elif state == "OBSTACLE":
        yellow = blink(4)
    elif state == "WARNING":
        yellow = True
        buzz = (t % 5.0) < 0.12
    elif state == "EMERGENCY":
        red = blink(2)
        buzz = blink(2)
    elif state == "STOPPED":
        red = True
    elif state == "SHUTDOWN":
        yellow = blink(1)
    if silenced:
        buzz = False
    return green, yellow, red, buzz


class Indicators(threading.Thread):
    def __init__(self, green, yellow, red, buzzer):
        super().__init__(name="indicators", daemon=True)
        self.outputs = (green, yellow, red, buzzer)
        self._state = "STARTING"
        self._silenced = False
        self._beep_until = 0.0
        self._beeps = []
        self._last = None
        self._running = True
        self._lock = threading.Lock()

    def set_state(self, state, silenced=False):
        with self._lock:
            self._state = state
            self._silenced = silenced

    def beep(self, count=1, on_s=0.08, off_s=0.1):
        """Short confirmation beeps (always audible, even when alarms are silenced)."""
        now = time.monotonic()
        with self._lock:
            self._beeps = [(now + i * (on_s + off_s), now + i * (on_s + off_s) + on_s) for i in range(count)]

    def lamp_test(self, seconds=1.0):
        for device in self.outputs[:3]:
            device.on()
        time.sleep(seconds)
        for device in self.outputs[:3]:
            device.off()

    def stop(self):
        self._running = False
        for device in self.outputs:
            device.off()

    def run(self):
        while self._running:
            now = time.monotonic()
            with self._lock:
                values = list(pattern(self._state, now, self._silenced))
                self._beeps = [b for b in self._beeps if b[1] > now]
                if any(start <= now < end for start, end in self._beeps):
                    values[3] = True
            if values != self._last:
                for device, value in zip(self.outputs, values):
                    device.on() if value else device.off()
                self._last = values
            time.sleep(0.05)
