"""Offline speech: espeak-ng text-to-speech played through the MAX98357A.

Every phrase has a key (see "phrases" in config/defaults.json). To use your
own recorded voice for a phrase, put a WAV file named <key>.wav in the
sounds/ folder, e.g. sounds/greeting.wav; it is played instead of the
synthetic voice.
"""

import logging
import os
import queue
import shutil
import subprocess
import threading

log = logging.getLogger(__name__)

PLAY_TIMEOUT_S = 60


class Speech(threading.Thread):
    def __init__(self, audio_cfg, sounds_dir, sim=False):
        super().__init__(name="speech", daemon=True)
        self.cfg = audio_cfg
        self.sounds_dir = sounds_dir
        self.sim = sim
        self._queue = queue.Queue(maxsize=20)
        self._procs = []
        self._lock = threading.Lock()
        self._interrupt = threading.Event()
        self._running = True
        self.last_spoken = ""
        self.speaking = False

    def configure(self, audio_cfg):
        self.cfg = audio_cfg

    def check(self):
        """Return (ok, message) describing whether audio output can work."""
        if self.sim:
            return True, "simulated"
        if not self.cfg.get("enabled", True):
            return False, "disabled in settings"
        if shutil.which("aplay") is None:
            return False, "aplay missing (install alsa-utils)"
        if shutil.which("espeak-ng") is None:
            return False, "espeak-ng missing"
        try:
            out = subprocess.run(["aplay", "-l"], capture_output=True, text=True, timeout=5).stdout
        except (OSError, subprocess.SubprocessError) as exc:
            return False, str(exc)
        if "card" not in out:
            return False, "no sound card (check dtoverlay=max98357a)"
        return True, "ok"

    def say(self, text, key=None, urgent=False):
        text = (text or "").strip()[:300]
        if not text:
            return
        if urgent:
            self._clear()
        try:
            self._queue.put_nowait((text, key))
        except queue.Full:
            log.warning("Speech queue full, dropped: %s", text)

    def _clear(self):
        try:
            while True:
                self._queue.get_nowait()
        except queue.Empty:
            pass
        self._interrupt.set()
        with self._lock:
            for proc in self._procs:
                if proc.poll() is None:
                    proc.kill()

    def stop(self):
        self._running = False
        self._clear()
        self._queue.put((None, None))

    def run(self):
        while self._running:
            text, key = self._queue.get()
            if text is None:
                break
            self._interrupt.clear()
            self.last_spoken = text
            self.speaking = True
            try:
                self._play(text, key)
            except Exception as exc:  # noqa: BLE001 - speech must never crash the robot
                log.warning("Speech failed: %s", exc)
            finally:
                self.speaking = False

    def _play(self, text, key):
        log.info("[SAY] %s", text)
        if self.sim:
            self._interrupt.wait(min(6.0, 0.06 * len(text)))  # pretend to speak
            return
        if not self.cfg.get("enabled", True):
            return
        wav = os.path.join(self.sounds_dir, key + ".wav") if key else None
        if wav and os.path.isfile(wav):
            proc = subprocess.Popen(["aplay", "-q", wav])
            with self._lock:
                self._procs = [proc]
            proc.wait(timeout=PLAY_TIMEOUT_S)
            return
        espeak = subprocess.Popen(
            ["espeak-ng", "--stdout", "-v", str(self.cfg["voice"]),
             "-s", str(int(self.cfg["speed"])), "-a", str(int(self.cfg["amplitude"]))],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        aplay = subprocess.Popen(["aplay", "-q"], stdin=espeak.stdout)
        espeak.stdout.close()  # aplay now owns the pipe
        with self._lock:
            self._procs = [espeak, aplay]
        try:
            espeak.stdin.write(text.encode("utf-8"))
            espeak.stdin.close()
        except BrokenPipeError:
            pass
        try:
            aplay.wait(timeout=PLAY_TIMEOUT_S)
            espeak.wait(timeout=5)
        except subprocess.TimeoutExpired:
            espeak.kill()
            aplay.kill()
