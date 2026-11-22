"""Robot core: starts every part, runs the 10 Hz control loop, handles commands.

Threads:
  startup      hardware checks + greeting, then becomes the control loop
  motion       50 Hz servo keyframes          (motion/gait.py)
  sensors-*    sensor polling                 (sensors/__init__.py)
  indicators   LEDs + buzzer                  (alerts/indicators.py)
  speech       voice output queue             (alerts/speech.py)
The web server (control/web_server.py) calls the public methods below.
"""

import logging
import os
import subprocess
import threading
import time
from collections import deque

from alerts.indicators import Indicators
from alerts.speech import Speech
from camera.stream import Camera
from hal import create_hardware
from motion.gait import MotionEngine, load_library
from motion.servos import ServoController
from safety.power import BatteryMonitor, percent
from safety.state_machine import MODES, Decision, Inputs, SafetyController
from sensors import SensorHub
from sensors.adc import GasMonitor
from sensors.system_health import SystemHealth, load_average

log = logging.getLogger(__name__)

CODE_DIR = os.path.dirname(os.path.abspath(__file__))
SOUNDS_DIR = os.path.join(CODE_DIR, "sounds")
LOOP_S = 0.1
SENSOR_WAIT_S = 8.0

SYSTEM_COMMANDS = {
    "shutdown": ["systemctl", "poweroff"],
    "reboot": ["systemctl", "reboot"],
    "maintenance": ["/usr/local/sbin/robot-maintenance", "--yes"],
    "protect": ["/usr/local/sbin/robot-protect", "--yes"],
}
CHECK_LABELS = {
    "audio": "Speaker", "servos": "Servo controller", "distance": "Distance sensor",
    "climate": "Temperature sensor", "gas": "Gas sensor", "battery": "Battery monitor",
    "camera": "Camera",
}


def fill_placeholders(text, values):
    """Replace {name} placeholders in a phrase (unknown ones are left as they are)."""
    for name, value in values.items():
        text = text.replace("{" + name + "}", str(value))
    return text


class Robot:
    def __init__(self, settings, sim=False):
        self.settings = settings
        self.sim = sim
        self.started = time.monotonic()
        self.hw = create_hardware(settings, sim)
        self.health = SystemHealth(self.hw.world)
        settings.is_protected = self.health.protected
        s = settings.snapshot()
        t = s["thresholds"]
        self.servos = ServoController(self.hw.pwm, self.hw.servo_enable, s["servos"],
                                      s["servo_types"], s["motion"]["max_speed_deg_per_s"])
        self.motion = MotionEngine(self.servos, load_library(set(self.servos.joints)), s["motion"])
        self.sensors = SensorHub(self.hw, s["calibration"], self.health)
        self.gas = GasMonitor(t["gas_warmup_s"], t["gas_warning_rise_v"], t["gas_danger_rise_v"],
                              t["gas_danger_absolute_v"])
        self.battery = BatteryMonitor(t["battery_warning_v"], t["battery_shutdown_v"], t["battery_shutdown_delay_s"])
        self.safety = SafetyController(t, s["motion"])
        self.indicators = Indicators(self.hw.led_green, self.hw.led_yellow, self.hw.led_red, self.hw.buzzer)
        self.speech = Speech(s["audio"], SOUNDS_DIR, sim)
        self.camera = Camera(s["camera"], sim)

        self._lock = threading.RLock()
        self._running = False
        self.ready = False
        self.state = "STARTING"
        self.decision = Decision("STARTING", "stop")
        self.checks = {}
        self.events = deque(maxlen=12)
        self._driver = None
        self._spoken_at = {}
        self._prev_hazards = set()
        self._prev_state = None
        self._system_action = None
        self._uv_announced = False
        self._mode_held = False
        self._wire_buttons()

    # ------------------------------------------------------------------ setup
    def _wire_buttons(self):
        if self.hw.button_estop is not None:
            self.hw.button_estop.when_pressed = lambda: self.estop("button")
        if self.hw.button_mode is not None:
            self.hw.button_mode.when_pressed = self._mode_pressed
            self.hw.button_mode.when_held = self._mode_held_2s
            self.hw.button_mode.when_released = self._mode_released

    def _mode_pressed(self):
        self._mode_held = False

    def _mode_held_2s(self):
        self._mode_held = True
        self.reset_estop()

    def _mode_released(self):
        if not self._mode_held and not self.safety.estopped:
            self.set_mode("auto" if self.safety.mode != "auto" else "monitor")

    def start(self):
        self._running = True
        threading.Thread(target=self._startup, name="startup", daemon=True).start()

    def _check(self, name, ok, message):
        self.checks[name] = {"ok": bool(ok), "label": CHECK_LABELS.get(name, name), "msg": message}
        (log.info if ok else log.warning)("check %-8s %s: %s", name, "OK" if ok else "FAIL", message)

    def _startup(self):
        try:
            self._run_startup_checks()
        except Exception:  # noqa: BLE001 - a failing check must not stop the robot
            log.exception("Startup checks crashed")
        self.ready = True
        self._event("Robot ready")
        self._control_loop()

    def _run_startup_checks(self):
        self.indicators.lamp_test(0.8)
        self.indicators.start()
        self.speech.start()
        self.indicators.beep(1)

        audio_ok, audio_msg = self.speech.check()
        self._check("audio", audio_ok, audio_msg)
        self.say("greeting")

        if self.servos.enable():
            self._check("servos", True, "PCA9685 found, home pose loaded")
        else:
            self._check("servos", False, self.hw.errors.get("servos", "PCA9685 not found") +
                        " - check I2C wiring (SDA pin 3, SCL pin 5) and address 0x40")
        self.motion.start()
        self.sensors.start()
        cam_ok, cam_msg = self.camera.check()
        self._check("camera", cam_ok, cam_msg)

        deadline = time.monotonic() + SENSOR_WAIT_S
        while time.monotonic() < deadline:
            snap = self.sensors.snapshot()
            if snap["dht_ok"] and snap["distance_ok"]:
                break
            time.sleep(0.25)
        snap = self.sensors.snapshot()
        self._check("distance", snap["distance_ok"], "%.0f cm" % snap["distance_cm"] if snap["distance_ok"] else
                    self.hw.errors.get("distance", "no echo - check wiring and the 1k/2k divider on ECHO"))
        self._check("climate", snap["dht_ok"], "%.1f C, %.0f %%" % (snap["temp_c"], snap["humidity"])
                    if snap["dht_ok"] else "no reading - check dtoverlay=dht11 and the 10k pull-up")
        if not snap["adc_ok"]:
            self._check("gas", False, self.hw.errors.get("adc", "MCP3008 not responding - check SPI wiring"))
        elif (snap["mq2_v"] or 0) < GasMonitor.ABSENT_BELOW_V:
            self._check("gas", False, "MQ-2 reads 0 V - check MQ-2 power and AO wire")
        else:
            self._check("gas", True, "%.2f V, warming up" % snap["mq2_v"])
        battery_v = snap["battery_v"]
        if battery_v is not None and battery_v >= 6.0:
            self._check("battery", True, "%.1f V (%s%%)" % (battery_v, percent(battery_v)))
        else:
            self._check("battery", True, "no battery detected (bench power supply)")

        failed = [name for name in ("distance", "climate", "gas") if not self.checks[name]["ok"]]
        if failed:
            for name in failed:
                self.speech.say("Warning. %s is not responding." % CHECK_LABELS[name])
        else:
            self.say("sensors_ok")
        if cam_ok:
            self.say("camera_ok")
        else:
            self.speech.say("Warning. Camera is not available.")
        if not self.checks["servos"]["ok"]:
            self.speech.say("Warning. Servo controller not found. Walking is disabled.")
        all_ok = all(c["ok"] for c in self.checks.values())
        self.say("ready" if all_ok else "ready_limited")
        self.say("connect_info")

    # --------------------------------------------------------------- control
    def _control_loop(self):
        while self._running:
            start = time.monotonic()
            try:
                self._tick(start)
            except Exception:  # noqa: BLE001 - the loop must never die
                log.exception("Control loop error")
            time.sleep(max(0.0, LOOP_S - (time.monotonic() - start)))

    def _tick(self, now):
        snap = self.sensors.snapshot()
        gas_level = self.gas.update(snap["mq2_v"] if snap["adc_ok"] else None, now)
        battery_level, shutdown_due = self.battery.update(snap["battery_v"], now)
        inputs = Inputs(
            distance_cm=snap["distance_cm"] if snap["distance_ok"] else None,
            temp_c=snap["temp_c"] if snap["dht_ok"] else None,
            gas_level=gas_level, battery_level=battery_level)
        with self._lock:
            if self._system_action:
                decision = Decision("SHUTDOWN", "stop", note="System %s in progress" % self._system_action)
            else:
                decision = self.safety.update(inputs, now)
            self.decision = decision
            self.state = decision.state
        if decision.motion == "freeze":
            self.motion.freeze()
        else:
            if self.motion.activity == "frozen":
                self.motion.unfreeze()
            if not self._system_action:
                self.motion.request(decision.motion, decision.speed)
        self.indicators.set_state(decision.state, self.safety.silenced(now))
        self._announce(decision, snap, now)
        if shutdown_due and not self._system_action:
            self._event("Battery critical: shutting down")
            self.say("battery_critical", urgent=True)
            self.system_action("shutdown", announce=False)

    def _announce(self, d, snap, now):
        keys = {h.key for h in d.hazards}
        for h in d.hazards:
            if h.key in self._prev_hazards:
                continue
            self._event(("DANGER: " if h.level == "danger" else "Warning: ") + h.text)
            if h.level == "danger":
                self.say("emergency", urgent=True, reason=h.text)
                self._spoken_at["emergency"] = now
                self.motion.gesture("alarm_signal")
            elif h.key == "battery":
                self.say("battery_low")
            elif h.key == "battery_critical":
                pass  # announced when the shutdown starts
            else:
                self.say("warning", reason=h.text)
        for key in self._prev_hazards - keys:
            self._event("Cleared: %s" % key)
        self._prev_hazards = keys

        if d.state == "EMERGENCY" and not self.safety.silenced(now):
            repeat = self.settings.get("audio", "emergency_repeat_s")
            if now - self._spoken_at.get("emergency", 0.0) >= repeat:
                reason = next((h.text for h in d.hazards if h.level == "danger"), "Danger")
                self.say("emergency", urgent=True, reason=reason)
                self._spoken_at["emergency"] = now

        if d.state == "OBSTACLE" and self._prev_state != "OBSTACLE":
            if now - self._spoken_at.get("obstacle", -100.0) > 8.0:
                self.say("obstacle")
                self._spoken_at["obstacle"] = now

        health = snap.get("health") or {}
        if health.get("undervoltage_now") and not self._uv_announced:
            self._uv_announced = True
            self._event("Power supply under-voltage detected")
            self.say("undervoltage")
        self._prev_state = d.state

    # ------------------------------------------------------------- commands
    def say(self, key, urgent=False, **values):
        phrases = self.settings.section("phrases")
        robot = self.settings.section("robot")
        fields = {"ssid": robot["wifi_ssid"].replace("-", " "), "address": robot["address"],
                  "name": robot["name"], "reason": ""}
        fields.update(values)
        text = fill_placeholders(phrases.get(key, key), fields)
        self.speech.say(text, key=key, urgent=urgent)

    def _event(self, text):
        self.events.appendleft({"t": time.strftime("%H:%M:%S"), "text": text})
        log.info("EVENT %s", text)

    def drive(self, client_id, x, y):
        if not self.ready:
            return "Robot is still starting"
        with self._lock:
            self._driver = client_id
            self.safety.drive(x, y, time.monotonic())
        return None

    def stop_drive(self):
        with self._lock:
            self.safety.stop_drive()
        self.motion.request("stop")

    def client_disconnected(self, client_id):
        with self._lock:
            if self._driver != client_id:
                return
            self._driver = None
            self.safety.stop_drive()
        self.motion.request("stop")

    def estop(self, source="phone"):
        with self._lock:
            already = self.safety.estopped
            self.safety.estop()
        self.motion.freeze()
        if not already:
            self._event("EMERGENCY STOP (%s)" % source)
            self.say("estop_on", urgent=True)
            self.indicators.beep(3)

    def reset_estop(self):
        with self._lock:
            if not self.safety.estopped:
                return False
            self.safety.reset_estop()
        self.motion.unfreeze()
        self._event("Emergency stop released")
        self.say("estop_off")
        self.indicators.beep(1)
        return True

    def set_mode(self, mode):
        with self._lock:
            ok = self.safety.set_mode(mode)
        if ok:
            self.motion.request("stop")
            self._event("Mode: %s" % mode)
            self.say("mode_" + mode)
        return ok

    def set_head(self, position):
        self.motion.set_head(float(position))

    def gesture(self, name):
        if self.safety.estopped:
            return "Emergency stop is on"
        if not self.motion.gesture(name):
            return "Stop walking first"
        return None

    def speak_text(self, text):
        text = " ".join(str(text).split())[:200]
        if text:
            self.speech.say(text)

    def silence(self):
        self.safety.silence(time.monotonic())
        self._event("Alarm sound silenced / acknowledged")

    def set_trim(self, joint, value):
        if joint not in self.servos.joints:
            return "Unknown servo"
        self.settings.update({"servos": {joint: {"trim": float(value)}}})
        self._apply_settings()
        return None

    def test_servo(self, joint, offset):
        if joint not in self.servos.joints:
            return "Unknown servo"
        offset = max(-45.0, min(45.0, float(offset)))
        frames = [({joint: offset}, 600, False), ({joint: offset}, 900, False), ({}, 600, False)]
        if self.safety.estopped or not self.motion.play("test:" + joint, frames):
            return "Stop the robot first (and release the emergency stop)"
        return None

    def servos_power(self, on):
        if on:
            if not self.servos.enable():
                return "Servo controller not available"
            self.reset_estop()
        else:
            self.estop("servos relaxed")
            self.servos.disable()
        self._event("Servos %s" % ("enabled" if on else "relaxed (limp)"))
        return None

    def update_settings(self, patch, save=False):
        self.settings.update(patch)
        self._apply_settings()
        if save:
            return self.settings.save()
        return {"persisted": False, "message": "Applied for this session (not saved)."}

    def _apply_settings(self):
        s = self.settings.snapshot()
        t = s["thresholds"]
        self.servos.configure(s["servos"], s["servo_types"], s["motion"]["max_speed_deg_per_s"])
        self.motion.configure(s["motion"])
        self.safety.configure(t, s["motion"])
        self.gas.configure(t["gas_warmup_s"], t["gas_warning_rise_v"], t["gas_danger_rise_v"],
                           t["gas_danger_absolute_v"])
        self.battery.configure(t["battery_warning_v"], t["battery_shutdown_v"], t["battery_shutdown_delay_s"])
        self.sensors.configure(s["calibration"])
        self.speech.configure(s["audio"])

    def system_action(self, action, announce=True):
        """shutdown / reboot / maintenance / protect. Runs in the background."""
        if action not in SYSTEM_COMMANDS:
            return {"ok": False, "message": "Unknown action"}
        protected = self.health.protected()
        if action == "protect" and protected:
            return {"ok": False, "message": "Already in protected mode."}
        if action == "maintenance" and not protected:
            return {"ok": False, "message": "Already in maintenance mode (SD card writable)."}
        with self._lock:
            if self._system_action:
                return {"ok": False, "message": "Busy: %s already in progress" % self._system_action}
            self._system_action = action
        threading.Thread(target=self._do_system_action, args=(action, announce),
                         name="system-action", daemon=True).start()
        messages = {"shutdown": "Shutting down. Wait 20 seconds until the Pi's green LED stops "
                                "flashing, then switch the power off.",
                    "reboot": "Rebooting. Reconnect in about one minute.",
                    "maintenance": "Switching to MAINTENANCE mode and rebooting.",
                    "protect": "Switching to PROTECTED mode and rebooting."}
        return {"ok": True, "message": messages[action]}

    def _do_system_action(self, action, announce):
        self._event("System: %s" % action)
        if announce:
            self.say("shutdown" if action == "shutdown" else "reboot", urgent=True)
        self.motion.unfreeze()
        self.motion.request("stop")
        time.sleep(1.0)
        if action == "shutdown":
            # Crouch so the robot is stable. The PCA9685 keeps holding this pose
            # until the main power switch is turned off.
            self.motion.gesture("rest")
        time.sleep(3.0)
        command = SYSTEM_COMMANDS[action]
        if self.sim:
            self._event("(simulator) would run: %s" % " ".join(command))
            time.sleep(2.0)
            with self._lock:
                self._system_action = None
            return
        try:
            subprocess.run(command, check=True, timeout=180)
        except (OSError, subprocess.SubprocessError) as exc:
            log.error("System action %s failed: %s", action, exc)
            self._event("System %s FAILED: %s" % (action, exc))
            with self._lock:
                self._system_action = None

    # --------------------------------------------------------------- status
    def status(self):
        now = time.monotonic()
        snap = self.sensors.snapshot()
        d = self.decision
        health = snap.get("health") or {}
        battery_v = snap["battery_v"]
        return {
            "name": self.settings.get("robot", "name"),
            "sim": self.sim,
            "ready": self.ready,
            "state": d.state,
            "mode": self.safety.mode,
            "modes": list(MODES),
            "estop": self.safety.estopped,
            "motion": d.motion,
            "speed": round(d.speed, 2),
            "activity": self.motion.activity,
            "note": d.note,
            "hazards": [{"level": h.level, "key": h.key, "text": h.text} for h in d.hazards],
            "silenced_s": round(self.safety.silence_left(now)),
            "system_action": self._system_action,
            "sensors": {
                "distance_cm": snap["distance_cm"], "distance_ok": snap["distance_ok"],
                "temp_c": snap["temp_c"], "humidity": snap["humidity"], "dht_ok": snap["dht_ok"],
                "gas_v": snap["mq2_v"], "gas_level": self.gas.level,
                "gas_baseline": round(self.gas.baseline, 3) if self.gas.baseline is not None else None,
                "gas_warmup_left": round(self.gas.warmup_left(now)),
                "battery_v": battery_v, "battery_pct": percent(battery_v),
                "battery_level": self.battery.level,
                "shutdown_in": self.battery.seconds_to_shutdown(now),
            },
            "health": {
                "cpu_temp_c": health.get("cpu_temp_c"),
                "protected": health.get("protected", self.health.protected()),
                "protected_after_reboot": health.get("protected_after_reboot"),
                "boot_readonly": health.get("boot_readonly"),
                "undervoltage_now": health.get("undervoltage_now", False),
                "undervoltage_seen": health.get("undervoltage_seen", False),
                "throttled_now": health.get("throttled_now", False),
                "load": load_average(),
            },
            "checks": self.checks,
            "camera": {"available": self.camera.available, "message": self.camera.message,
                       "viewers": self.camera.viewers},
            "speech": {"last": self.speech.last_spoken, "speaking": self.speech.speaking},
            "servos": {"available": self.servos.available, "enabled": self.servos.enabled,
                       "angles": self.servos.angles()},
            "events": list(self.events),
            "uptime_s": int(now - self.started),
        }

    def stop(self):
        """Stop the program. Servos keep holding their pose (the PCA9685 runs on its own)."""
        self._running = False
        self.sensors.stop()
        self.motion.stop_thread()
        self.camera.stop()
        self.speech.stop()
        self.indicators.stop()
