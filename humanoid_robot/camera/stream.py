"""Raspberry Pi camera -> MJPEG stream for the phone dashboard.

Uses picamera2 with the Pi's hardware MJPEG encoder (light on the Pi 3 CPU).
The camera only runs while someone is watching, and stops 10 seconds after
the last viewer leaves, to save power and keep the Pi cool.
"""

import io
import logging
import threading

log = logging.getLogger(__name__)

IDLE_STOP_S = 10.0


class FrameBuffer(io.BufferedIOBase):
    """picamera2 writes one complete JPEG per write() call."""

    def __init__(self):
        super().__init__()
        self.frame = None
        self.frame_id = 0
        self.cond = threading.Condition()

    def writable(self):
        return True

    def write(self, buf):
        with self.cond:
            self.frame = bytes(buf)
            self.frame_id += 1
            self.cond.notify_all()
        return len(buf)

    def wait_frame(self, last_id, timeout=1.0):
        """Block until a frame newer than last_id exists. Returns (frame, id) or (None, last_id)."""
        with self.cond:
            self.cond.wait_for(lambda: self.frame_id != last_id, timeout)
            if self.frame_id == last_id:
                return None, last_id
            return self.frame, self.frame_id


class Camera:
    def __init__(self, cfg, sim=False):
        self.cfg = cfg
        self.sim = sim
        self.buffer = FrameBuffer()
        self.available = False
        self.message = "not checked"
        self._lock = threading.Lock()
        self._viewers = 0
        self._cam = None
        self._stop_timer = None

    def check(self):
        """Detect the camera without starting it. Returns (ok, message)."""
        if not self.cfg.get("enabled", True):
            self.available, self.message = False, "disabled in settings"
        elif self.sim:
            self.available, self.message = False, "no camera in simulator"
        else:
            try:
                from picamera2 import Picamera2
                cameras = Picamera2.global_camera_info()
                if cameras:
                    self.available, self.message = True, cameras[0].get("Model", "camera")
                else:
                    self.available, self.message = False, "no camera detected (check ribbon cable)"
            except Exception as exc:  # noqa: BLE001
                self.available, self.message = False, "picamera2 error: %s" % exc
        return self.available, self.message

    @property
    def viewers(self):
        return self._viewers

    def acquire(self):
        """A viewer connected. Starts the camera if needed. Returns True if streaming."""
        with self._lock:
            if not self.available:
                return False
            self._viewers += 1
            if self._stop_timer:
                self._stop_timer.cancel()
                self._stop_timer = None
            if self._cam is None:
                try:
                    self._start()
                except Exception as exc:  # noqa: BLE001
                    log.error("Camera start failed: %s", exc)
                    self._viewers -= 1
                    self._close()
                    return False
            return True

    def release(self):
        with self._lock:
            self._viewers = max(0, self._viewers - 1)
            if self._viewers == 0 and self._cam is not None and self._stop_timer is None:
                self._stop_timer = threading.Timer(IDLE_STOP_S, self._idle_stop)
                self._stop_timer.daemon = True
                self._stop_timer.start()

    def _idle_stop(self):
        with self._lock:
            self._stop_timer = None
            if self._viewers == 0:
                self._close()

    def _start(self):
        from picamera2 import Picamera2
        from picamera2.outputs import FileOutput
        cam = Picamera2()
        self._cam = cam
        config = cam.create_video_configuration(
            main={"size": (int(self.cfg["width"]), int(self.cfg["height"]))},
            controls={"FrameRate": float(self.cfg["fps"])})
        cam.configure(config)
        try:
            from picamera2.encoders import MJPEGEncoder
            encoder = MJPEGEncoder()
        except ImportError:  # older picamera2: software JPEG
            from picamera2.encoders import JpegEncoder
            encoder = JpegEncoder(q=70)
        cam.start_recording(encoder, FileOutput(self.buffer))
        log.info("Camera streaming started")

    def _close(self):
        if self._cam is None:
            return
        try:
            self._cam.stop_recording()
        except Exception:  # noqa: BLE001
            pass
        try:
            self._cam.close()
        except Exception:  # noqa: BLE001
            pass
        self._cam = None
        log.info("Camera stopped")

    def stop(self):
        with self._lock:
            if self._stop_timer:
                self._stop_timer.cancel()
            self._close()
