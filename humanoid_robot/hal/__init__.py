"""Hardware abstraction: creates real Raspberry Pi devices or simulated ones.

Every device is created separately. If one part is missing or wired wrong,
it is replaced by a harmless stand-in and the error is reported on the web
page and in the startup speech; the rest of the robot keeps working.
"""

import logging
import os
from dataclasses import dataclass, field

from config import pins

log = logging.getLogger(__name__)


def is_raspberry_pi():
    try:
        with open("/proc/device-tree/model", "r") as f:
            return "Raspberry Pi" in f.read()
    except OSError:
        return False


def sim_requested():
    return os.environ.get("ROBOT_SIM", "").lower() in ("1", "true", "yes")


class NullOutput:
    """Stand-in for an LED/buzzer/output that failed to initialise."""
    value = 0

    def on(self):
        pass

    def off(self):
        pass

    def close(self):
        pass


@dataclass
class Hardware:
    sim: bool
    pwm: object = None              # PCA9685 or SimPWM; None if the servo driver is missing
    servo_enable: object = None     # PCA9685 OE line; on() = servo signals enabled
    led_green: object = None
    led_yellow: object = None
    led_red: object = None
    buzzer: object = None
    button_estop: object = None
    button_mode: object = None
    ultrasonic: object = None
    dht: object = None
    adc: object = None
    world: object = None            # SimWorld in simulator mode
    errors: dict = field(default_factory=dict)

    def close(self):
        for name in ("pwm", "servo_enable", "led_green", "led_yellow", "led_red", "buzzer",
                     "button_estop", "button_mode", "ultrasonic", "adc"):
            device = getattr(self, name)
            close = getattr(device, "close", None)
            if close:
                try:
                    close()
                except Exception:  # noqa: BLE001 - best effort on shutdown
                    pass


def _try(hw, key, factory, fallback=None):
    try:
        return factory()
    except Exception as exc:  # noqa: BLE001 - any driver error must not stop the robot
        log.error("%s failed to start: %s", key, exc)
        hw.errors[key] = str(exc)
        return fallback


def create_hardware(settings, sim):
    hw = Hardware(sim=sim)
    calibration = settings.section("calibration")
    if sim:
        from hal.sim import SimADC, SimButton, SimDHT, SimOutput, SimPWM, SimUltrasonic, SimWorld
        hw.world = SimWorld()
        hw.pwm = SimPWM()
        hw.servo_enable = SimOutput("servo_enable")
        hw.led_green, hw.led_yellow, hw.led_red = SimOutput("green"), SimOutput("yellow"), SimOutput("red")
        hw.buzzer = SimOutput("buzzer")
        hw.button_estop, hw.button_mode = SimButton("estop"), SimButton("mode")
        hw.ultrasonic = SimUltrasonic(hw.world)
        hw.dht = SimDHT(hw.world)
        hw.adc = SimADC(hw.world, calibration, pins.ADC_CH_MQ2, pins.ADC_CH_BATTERY)
        return hw

    from gpiozero import LED, Button, Buzzer, DigitalOutputDevice

    from hal.pca9685 import PCA9685
    from sensors.adc import MCP3008
    from sensors.dht22 import DHT22
    from sensors.ultrasonic import Ultrasonic

    # OE starts enabled (LOW). After a cold boot the PCA9685 outputs are off
    # anyway; after a program restart this keeps the robot holding its pose.
    hw.servo_enable = _try(hw, "servo_enable", lambda: DigitalOutputDevice(
        pins.PCA9685_OE, active_high=False, initial_value=True), NullOutput())
    hw.pwm = _try(hw, "servos", lambda: PCA9685(pins.I2C_BUS, pins.PCA9685_ADDRESS))
    hw.led_green = _try(hw, "led_green", lambda: LED(pins.LED_GREEN), NullOutput())
    hw.led_yellow = _try(hw, "led_yellow", lambda: LED(pins.LED_YELLOW), NullOutput())
    hw.led_red = _try(hw, "led_red", lambda: LED(pins.LED_RED), NullOutput())
    hw.buzzer = _try(hw, "buzzer", lambda: Buzzer(pins.BUZZER), NullOutput())
    hw.button_estop = _try(hw, "button_estop", lambda: Button(
        pins.BUTTON_ESTOP, pull_up=True, bounce_time=0.05))
    hw.button_mode = _try(hw, "button_mode", lambda: Button(
        pins.BUTTON_MODE, pull_up=True, bounce_time=0.05, hold_time=2.0))
    hw.ultrasonic = _try(hw, "distance", lambda: Ultrasonic(
        pins.ULTRASONIC_TRIGGER, pins.ULTRASONIC_ECHO))
    hw.dht = DHT22()
    hw.adc = _try(hw, "adc", lambda: MCP3008(pins.SPI_BUS, pins.SPI_DEVICE, calibration["adc_vref"]))
    return hw
