"""SensorHub: reads every sensor in background threads.

The control loop only ever reads the latest snapshot, so a slow or broken
sensor can never block the robot. Fast thread: distance + analog inputs.
Slow thread: DHT22 (max once per 2 s) + Raspberry Pi health.
"""

import copy
import logging
import threading
import time

from config import pins
from sensors.ultrasonic import median

log = logging.getLogger(__name__)

DHT_PERIOD_S = 3.0
HEALTH_PERIOD_S = 5.0
ADC_PERIOD_S = 0.5
DISTANCE_PERIOD_S = 0.1
DHT_STALE_S = 15.0
DISTANCE_FAILS_FOR_FAULT = 3


class SensorHub:
    def __init__(self, hw, calibration, health):
        self.hw = hw
        self.calibration = calibration
        self.health = health
        self._lock = threading.Lock()
        self._running = False
        self._recent_cm = []
        self._distance_fails = 0
        self._data = {
            "distance_cm": None, "distance_ok": False,
            "temp_c": None, "humidity": None, "dht_ok": False, "dht_time": None,
            "mq2_v": None, "battery_v": None, "adc_ok": hw.adc is not None,
            "health": {}, "updated": None,
        }

    def configure(self, calibration):
        self.calibration = calibration

    def start(self):
        self._running = True
        threading.Thread(target=self._fast_loop, name="sensors-fast", daemon=True).start()
        threading.Thread(target=self._slow_loop, name="sensors-slow", daemon=True).start()

    def stop(self):
        self._running = False

    def snapshot(self):
        with self._lock:
            data = copy.deepcopy(self._data)
        if data["dht_time"] is not None and time.monotonic() - data["dht_time"] > DHT_STALE_S:
            data["dht_ok"] = False
        return data

    def _set(self, **values):
        with self._lock:
            self._data.update(values)
            self._data["updated"] = time.monotonic()

    # ------------------------------------------------------------------
    def _read_distance(self):
        sensor = self.hw.ultrasonic
        if sensor is None:
            self._set(distance_cm=None, distance_ok=False)
            return
        try:
            cm = sensor.read_cm()
        except Exception as exc:  # noqa: BLE001
            log.debug("distance read failed: %s", exc)
            cm = None
        if cm is None:
            self._distance_fails += 1
            if self._distance_fails >= DISTANCE_FAILS_FOR_FAULT:
                self._recent_cm.clear()
                self._set(distance_cm=None, distance_ok=False)
            return
        self._distance_fails = 0
        self._recent_cm = (self._recent_cm + [cm])[-3:]
        self._set(distance_cm=median(self._recent_cm), distance_ok=True)

    def _read_adc(self):
        adc = self.hw.adc
        if adc is None:
            self._set(adc_ok=False, mq2_v=None, battery_v=None)
            return
        cal = self.calibration
        try:
            mq2 = adc.read_voltage(pins.ADC_CH_MQ2) * cal["mq2_divider_ratio"]
            battery = adc.read_voltage(pins.ADC_CH_BATTERY) * cal["battery_divider_ratio"]
            self._set(adc_ok=True, mq2_v=round(mq2, 3), battery_v=round(battery, 2))
        except Exception as exc:  # noqa: BLE001
            log.warning("ADC read failed: %s", exc)
            self._set(adc_ok=False, mq2_v=None, battery_v=None)

    def _read_dht(self):
        try:
            temp, humidity = self.hw.dht.read()
            self._set(temp_c=round(temp, 1), humidity=round(humidity, 1), dht_ok=True,
                      dht_time=time.monotonic())
        except Exception as exc:  # noqa: BLE001 - DHT reads fail now and then; retry later
            log.debug("DHT22 read failed: %s", exc)

    def _fast_loop(self):
        next_adc = 0.0
        while self._running:
            start = time.monotonic()
            self._read_distance()
            if start >= next_adc:
                self._read_adc()
                next_adc = start + ADC_PERIOD_S
            time.sleep(max(0.0, DISTANCE_PERIOD_S - (time.monotonic() - start)))

    def _slow_loop(self):
        next_dht = 0.0
        next_health = 0.0
        while self._running:
            now = time.monotonic()
            if now >= next_dht:
                self._read_dht()
                next_dht = time.monotonic() + DHT_PERIOD_S
            if now >= next_health:
                try:
                    self._set(health=self.health.read())
                except Exception as exc:  # noqa: BLE001
                    log.warning("health read failed: %s", exc)
                next_health = now + HEALTH_PERIOD_S
            time.sleep(0.2)
