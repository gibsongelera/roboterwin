"""DHT22 temperature/humidity through the Linux kernel driver.

config.txt contains  dtoverlay=dht11,gpiopin=4  (the "dht11" driver also
handles DHT22/AM2302). The kernel does the time-critical bit-banging, which
is far more reliable than doing it from Python. Values appear as an IIO
device in /sys/bus/iio/devices/.

The sensor may answer at most every 2 seconds and single reads sometimes
fail (EIO / timeout); the caller simply tries again later.
"""

import glob
import os

IIO_GLOB = "/sys/bus/iio/devices/iio:device*"


def find_device():
    for path in sorted(glob.glob(IIO_GLOB)):
        try:
            with open(os.path.join(path, "name"), "r") as f:
                if f.read().strip().startswith("dht11"):
                    return path
        except OSError:
            continue
    return None


class DHT22:
    def __init__(self):
        self.path = find_device()

    @property
    def available(self):
        return self.path is not None

    def read(self):
        """Return (temperature_c, humidity_percent). Raises OSError on failure."""
        if self.path is None:
            self.path = find_device()
            if self.path is None:
                raise OSError("DHT22 driver not loaded (check dtoverlay=dht11 in config.txt)")
        with open(os.path.join(self.path, "in_temp_input"), "r") as f:
            temp = int(f.read().strip()) / 1000.0
        with open(os.path.join(self.path, "in_humidityrelative_input"), "r") as f:
            humidity = int(f.read().strip()) / 1000.0
        if not (-40.0 <= temp <= 80.0 and 0.0 <= humidity <= 100.0):
            raise OSError("DHT22 value out of range: %.1f C %.1f %%" % (temp, humidity))
        return temp, humidity
