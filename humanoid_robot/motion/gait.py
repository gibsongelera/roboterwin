"""Keyframe motion engine: walking gaits, gestures, head and safe stopping.

Runs in its own thread at 50 Hz. Poses move smoothly between keyframes
(cosine easing) and ServoController adds a hard speed limit on top.

Stopping rules:
* "stop"   - interrupts a step immediately and returns to the home pose.
* freeze() - software emergency stop: holds the current pose exactly
             (cutting servo power would make a standing robot fall over).
"""

import json
import logging
import math
import os
import threading
import time
from collections import deque

log = logging.getLogger(__name__)

TICK_S = 0.02
MAX_OFFSET = 90.0
WALK_GAITS = {"forward": "walk_forward", "backward": "walk_backward",
              "left": "turn_left", "right": "turn_right"}
DEFAULT_LIBRARY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gaits.json")


def ease(t):
    """Cosine ease-in/out, 0..1 -> 0..1."""
    t = max(0.0, min(1.0, t))
    return 0.5 - 0.5 * math.cos(math.pi * t)


def blend(a, b, t):
    keys = set(a) | set(b)
    return {k: a.get(k, 0.0) + (b.get(k, 0.0) - a.get(k, 0.0)) * t for k in keys}


def _clean_frame(frame, joints):
    return {k: max(-MAX_OFFSET, min(MAX_OFFSET, float(v)))
            for k, v in frame.items() if k in joints and isinstance(v, (int, float))}


def _mirror_name(name):
    if name.startswith("R_"):
        return "L_" + name[2:]
    if name.startswith("L_"):
        return "R_" + name[2:]
    return name


def _derive(frames, spec):
    negate = set(spec.get("negate", []))
    out = []
    for frame in frames:
        new = {}
        for k, v in frame.items():
            if spec.get("mirror"):
                name = _mirror_name(k)
                if name.endswith("ANKLE") or name == "HEAD":
                    v = -v
            else:
                name = k
            new[name] = -v if name in negate else v
        out.append(new)
    return out


def load_library(joints, path=DEFAULT_LIBRARY):
    """Load gaits.json and return {"gaits": {name: [pose]}, "gestures": {name: [(pose, ms, hold)]}}."""
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    gaits = {}
    pending = dict(raw.get("gaits", {}))
    for _ in range(len(pending) + 1):  # resolve "derive" chains
        for name, spec in list(pending.items()):
            if "frames" in spec:
                gaits[name] = [_clean_frame(fr, joints) for fr in spec["frames"]]
                del pending[name]
            elif spec.get("derive", {}).get("from") in gaits:
                gaits[name] = _derive(gaits[spec["derive"]["from"]], spec["derive"])
                del pending[name]
    for name in pending:
        log.error("Gait %s could not be built (bad 'derive')", name)
    gestures = {}
    for name, frames in raw.get("gestures", {}).items():
        gestures[name] = [(_clean_frame(fr, joints), max(50, int(fr.get("ms", 400))), bool(fr.get("hold")))
                          for fr in frames]
    return {"gaits": gaits, "gestures": gestures}


class MotionEngine(threading.Thread):
    def __init__(self, servos, library, motion_cfg):
        super().__init__(name="motion", daemon=True)
        self.servos = servos
        self.library = library
        self._lock = threading.Lock()
        self._running = True
        self.home = {name: 0.0 for name in servos.joints}
        self.configure(motion_cfg)
        self._pose = dict(self.home)
        self._seg_from = dict(self.home)
        self._seg_to = dict(self.home)
        self._seg_start = 0.0
        self._seg_dur = 0.0
        self._gait = None
        self._frame = 0
        self._gesture = deque()
        self._gesture_name = None
        self._gesture_has_head = False
        self._holding = False
        self._request = ("stop", 0.0)
        self._frozen = False
        self._head = 0.0

    def configure(self, motion_cfg):
        with self._lock:
            self.step_s = motion_cfg["step_ms"] / 1000.0
            self.home_s = motion_cfg["home_transition_ms"] / 1000.0
            self.head_range = float(motion_cfg["head_range_deg"])

    # ----- commands (any thread) ------------------------------------------
    def request(self, motion, speed=1.0):
        """motion: 'stop', 'forward', 'backward', 'left' or 'right'."""
        with self._lock:
            if motion not in WALK_GAITS:
                motion = "stop"
            previous = self._request[0]
            self._request = (motion, max(0.0, min(1.0, speed)))
            if motion == "stop" and previous != "stop" and self._gait and not self._frozen:
                self._gait = None
                self._seg_dur = 0.0  # interrupt the step: next tick heads home

    def gesture(self, name):
        """Play a named gesture from gaits.json. Refused while walking or frozen."""
        frames = self.library["gestures"].get(name)
        return frames is not None and self.play(name, frames)

    def play(self, name, frames):
        """Play keyframes [(pose, ms, hold), ...] once."""
        with self._lock:
            if self._frozen or self._gait or self._request[0] != "stop":
                return False
            self._gesture = deque(frames)
            self._gesture_name = name
            self._gesture_has_head = any("HEAD" in pose for pose, _ms, _hold in frames)
            self._holding = False
            self._seg_dur = 0.0  # start on the next tick
            return True

    def set_head(self, position):
        """position -1..1 (left is +)."""
        with self._lock:
            self._head = max(-1.0, min(1.0, position)) * self.head_range

    def freeze(self):
        with self._lock:
            self._frozen = True
            self._gait = None
            self._gesture.clear()
            self._gesture_name = None

    def unfreeze(self):
        with self._lock:
            if self._frozen:
                self._frozen = False
                self._request = ("stop", 0.0)
                self._seg_dur = 0.0  # next tick heads home from the held pose

    def stop_thread(self):
        self._running = False

    @property
    def activity(self):
        with self._lock:
            if self._frozen:
                return "frozen"
            if self._gait:
                return "walking"
            if self._gesture_name:
                return "gesture:" + self._gesture_name
            if self._holding:
                return "resting"
            return "idle"

    # ----- engine ----------------------------------------------------------
    def _start(self, now, target, duration):
        self._seg_from = dict(self._pose)
        self._seg_to = dict(target)
        self._seg_start = now
        self._seg_dur = max(0.05, duration)

    def tick(self, now):
        """Advance the motion and return the desired pose (joint -> offset)."""
        with self._lock:
            if self._frozen:
                return dict(self._pose)
            if self._seg_dur > 0:
                t = (now - self._seg_start) / self._seg_dur
                self._pose = blend(self._seg_from, self._seg_to, ease(t))
                done = t >= 1.0
            else:
                done = True
            if done:
                self._next_segment(now)
            pose = dict(self._pose)
            if "HEAD" in pose and not (self._gesture_name and self._gesture_has_head):
                pose["HEAD"] = pose["HEAD"] + self._head
            return pose

    def _next_segment(self, now):
        motion, speed = self._request
        gait_name = WALK_GAITS.get(motion)
        frames = self.library["gaits"].get(gait_name) if gait_name else None
        if frames:
            if self._gait != gait_name:
                self._gait, self._frame = gait_name, 0
                self._gesture.clear()
                self._gesture_name = None
            else:
                self._frame = (self._frame + 1) % len(frames)
            self._holding = False
            target = dict(self.home)
            target.update(frames[self._frame])
            self._start(now, target, self.step_s / (0.4 + 0.6 * max(speed, 0.0)))
            return
        self._gait = None
        if self._gesture:
            pose, ms, hold = self._gesture.popleft()
            target = dict(self.home)
            target.update(pose)
            self._holding = hold
            self._start(now, target, ms / 1000.0)
            return
        self._gesture_name = None
        if not self._holding and any(abs(v) > 0.01 for v in self._pose.values()):
            self._start(now, self.home, self.home_s)
        else:
            self._seg_dur = 0.0

    def run(self):
        last = time.monotonic()
        while self._running:
            now = time.monotonic()
            pose = self.tick(now)
            self.servos.write(pose, now - last)
            last = now
            time.sleep(max(0.0, TICK_S - (time.monotonic() - now)))
