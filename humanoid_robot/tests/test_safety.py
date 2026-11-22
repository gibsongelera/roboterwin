import pytest

from config.settings import Settings
from safety.power import BatteryMonitor, percent
from safety.state_machine import Inputs, SafetyController, classify_drive
from sensors.adc import GasMonitor
from alerts.indicators import pattern


def _controller(tmp_path):
    s = Settings(str(tmp_path)).snapshot()
    return SafetyController(s["thresholds"], s["motion"])


def clear():
    return Inputs(distance_cm=150, temp_c=24, gas_level="normal", battery_level="ok")


def test_classify_drive():
    assert classify_drive(0, 0.1) == ("stop", 0.0)
    assert classify_drive(0, 1)[0] == "forward"
    assert classify_drive(0, -1)[0] == "backward"
    assert classify_drive(-1, 0.2)[0] == "left"
    assert classify_drive(1, 0)[1] == pytest.approx(1.0)


def test_manual_drive_and_watchdog(tmp_path):
    c = _controller(tmp_path)
    c.drive(0, 1, now=10.0)
    d = c.update(clear(), 10.1)
    assert (d.state, d.motion) == ("MOVING", "forward")
    d = c.update(clear(), 10.7)  # no command for 0.7 s > 0.5 s watchdog
    assert (d.state, d.motion) == ("READY", "stop")


def test_obstacle_blocks_forward_only(tmp_path):
    c = _controller(tmp_path)
    near = clear()
    near.distance_cm = 10
    c.drive(0, 1, now=0)
    d = c.update(near, 0.1)
    assert (d.state, d.motion, d.blocked) == ("OBSTACLE", "stop", True)
    c.drive(0, -1, now=0.2)
    assert c.update(near, 0.3).motion == "backward"
    c.drive(1, 0, now=0.4)
    assert c.update(near, 0.5).motion == "right"


def test_auto_mode_turns_away_until_clear(tmp_path):
    c = _controller(tmp_path)
    c.set_mode("auto")
    assert c.update(clear(), 0).motion == "forward"
    near = clear()
    near.distance_cm = 20
    d = c.update(near, 1)
    assert (d.motion, d.state) == ("left", "OBSTACLE")
    mid = clear()
    mid.distance_cm = 32  # above stop distance but below clear distance: keep turning
    assert c.update(mid, 2).motion == "left"
    assert c.update(clear(), 3).motion == "forward"


def test_auto_mode_stops_when_distance_sensor_broken(tmp_path):
    c = _controller(tmp_path)
    c.set_mode("auto")
    blind = clear()
    blind.distance_cm = None
    assert c.update(blind, 0).motion == "stop"


def test_gas_danger_is_emergency_and_stops(tmp_path):
    c = _controller(tmp_path)
    smoke = clear()
    smoke.gas_level = "danger"
    c.drive(0, 1, now=0)
    d = c.update(smoke, 0.1)
    assert (d.state, d.motion) == ("EMERGENCY", "stop")
    # after acknowledging, the operator may drive the robot away
    c.silence(0.2)
    c.drive(0, -1, now=0.3)
    d = c.update(smoke, 0.4)
    assert (d.state, d.motion) == ("EMERGENCY", "backward")


def test_heat_levels(tmp_path):
    c = _controller(tmp_path)
    warm = clear()
    warm.temp_c = 48
    assert c.update(warm, 0).state == "WARNING"
    warm.temp_c = 60
    assert c.update(warm, 0).state == "EMERGENCY"


def test_estop_latches_until_reset(tmp_path):
    c = _controller(tmp_path)
    c.estop()
    c.drive(0, 1, now=0)
    d = c.update(clear(), 0.1)
    assert (d.state, d.motion) == ("STOPPED", "freeze")
    c.reset_estop()
    assert c.update(clear(), 0.2).state == "READY"


def test_gas_monitor_baseline():
    g = GasMonitor(warmup_s=10, warning_rise_v=0.4, danger_rise_v=0.8, danger_absolute_v=2.8)
    for t in range(10):
        assert g.update(0.6, t) == "warmup"
    assert g.update(0.6, 11) == "normal"
    assert g.update(1.1, 12) == "warning"
    assert g.update(1.5, 13) == "danger"
    assert g.update(0.0, 14) == "absent"
    assert g.update(None, 15) == "error"


def test_gas_absolute_limit_catches_smoky_startup():
    g = GasMonitor(warmup_s=10, warning_rise_v=0.4, danger_rise_v=0.8, danger_absolute_v=2.8)
    for t in range(10):
        g.update(2.6, t)          # switched on in a smoky room: bad baseline
    assert g.update(2.7, 11) == "normal"
    assert g.update(3.0, 12) == "danger"


def test_battery_shutdown_needs_sustained_low_voltage():
    b = BatteryMonitor(warning_v=13.6, shutdown_v=13.2, delay_s=30)
    assert b.update(None, 0) == ("absent", False)
    assert b.update(5.0, 0) == ("absent", False)   # bench power: never shut down
    assert b.update(15.5, 0) == ("ok", False)
    assert b.update(13.5, 1) == ("low", False)
    assert b.update(13.0, 2) == ("critical", False)
    assert b.update(13.0, 20) == ("critical", False)
    assert b.update(13.0, 33) == ("critical", True)
    assert b.update(15.0, 40) == ("ok", False)
    assert percent(16.8) == 100 and percent(13.2) == 0 and percent(3.0) is None


def test_indicator_patterns():
    assert pattern("READY", 0) == (True, False, False, False)
    assert pattern("EMERGENCY", 0.1)[2:] == (True, True)
    assert pattern("EMERGENCY", 0.1, silenced=True)[3] is False
    assert pattern("STOPPED", 3) == (False, False, True, False)
