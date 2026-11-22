import pytest

from config.settings import Settings
from hal.pca9685 import PCA9685, period_us_for, prescale_for, us_to_ticks
from hal.sim import SimOutput, SimPWM
from motion.gait import MotionEngine, ease, load_library
from motion.servos import Joint, ServoController


class FakeBus:
    def __init__(self):
        self.regs = {0x00: 0x11}
        self.blocks = []

    def write_byte_data(self, addr, reg, value):
        self.regs[reg] = value

    def read_byte_data(self, addr, reg):
        return self.regs.get(reg, 0)

    def write_i2c_block_data(self, addr, reg, data):
        self.blocks.append((reg, list(data)))


def test_pca9685_math():
    assert prescale_for(50) == 121
    period = period_us_for(121)
    assert 19900 < period < 20100
    assert us_to_ticks(1500, 20000) == 307
    assert us_to_ticks(99999, 20000) == 4095


def test_pca9685_writes_channel_registers():
    bus = FakeBus()
    pwm = PCA9685(bus=bus)
    assert bus.regs[0xFE] == 121
    pwm.set_pulse_us(2, 1500)
    reg, data = bus.blocks[-1]
    assert reg == 0x06 + 4 * 2
    assert data[:2] == [0, 0] and (data[2] | data[3] << 8) == us_to_ticks(1500, pwm.period_us)


def _servos(tmp_path):
    s = Settings(str(tmp_path)).snapshot()
    return ServoController(SimPWM(), SimOutput(), s["servos"], s["servo_types"], 240), s


def test_joint_invert_trim_and_limits():
    types = {"min_us": 500, "max_us": 2500, "range_deg": 180}
    j = Joint("L_HIP", {"channel": 3, "type": "MG996R", "home": 90, "min": 30, "max": 150,
                        "invert": True, "trim": 5}, types)
    assert j.servo_angle(10) == 85          # inverted: 90 + 5 - 10
    assert j.servo_angle(-200) == 150       # clamped to max
    assert j.pulse_us(90) == 1500


def test_servo_speed_limit(tmp_path):
    servos, _ = _servos(tmp_path)
    servos.enable()
    servos.write({"R_HIP": 90}, 0.02)
    assert servos.current["R_HIP"] == pytest.approx(240 * 0.02)


def test_disabled_servos_do_not_move(tmp_path):
    servos, _ = _servos(tmp_path)
    servos.write({"R_HIP": 30}, 1.0)
    assert servos.current["R_HIP"] == 0


def test_ease():
    assert ease(0) == 0 and ease(1) == 1 and ease(0.5) == pytest.approx(0.5)


def test_library_derives_gaits(tmp_path):
    servos, _ = _servos(tmp_path)
    lib = load_library(set(servos.joints))
    assert set(lib["gaits"]) == {"walk_forward", "walk_backward", "turn_left", "turn_right"}
    fwd, back = lib["gaits"]["walk_forward"], lib["gaits"]["walk_backward"]
    assert back[0]["R_HIP"] == -fwd[0]["R_HIP"]
    left, right = lib["gaits"]["turn_left"], lib["gaits"]["turn_right"]
    assert right[1]["R_KNEE"] == left[1]["L_KNEE"]       # mirrored leg
    assert right[1]["R_ANKLE"] == -left[1]["R_ANKLE"]    # opposite lean


def _engine(tmp_path):
    servos, s = _servos(tmp_path)
    return MotionEngine(servos, load_library(set(servos.joints)), s["motion"])


def test_walk_then_stop_returns_home(tmp_path):
    eng = _engine(tmp_path)
    eng.request("forward", 1.0)
    t = 0.0
    for _ in range(100):
        t += 0.02
        pose = eng.tick(t)
    assert eng.activity == "walking"
    assert any(abs(v) > 1 for v in pose.values())
    eng.request("stop")
    for _ in range(100):
        t += 0.02
        pose = eng.tick(t)
    assert eng.activity == "idle"
    assert all(abs(v) < 0.01 for v in pose.values())


def test_freeze_holds_pose_and_blocks_gestures(tmp_path):
    eng = _engine(tmp_path)
    eng.request("forward", 1.0)
    for i in range(20):
        eng.tick(i * 0.02)
    eng.freeze()
    held = eng.tick(1.0)
    assert eng.tick(5.0) == held
    assert eng.gesture("wave") is False
    assert eng.activity == "frozen"


def test_gesture_refused_while_walking(tmp_path):
    eng = _engine(tmp_path)
    eng.request("left", 0.5)
    eng.tick(0.0)
    assert eng.gesture("wave") is False
    eng.request("stop")
    assert eng.gesture("wave") is True
