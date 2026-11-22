#!/usr/bin/env python3
"""Humanoid Robot - main program.

On the robot this is started automatically at boot by systemd
(system/humanoid-robot.service). On a PC it runs in simulator mode:

    python main.py --sim            then open http://localhost:8080
"""

import argparse
import logging
import os
import sys
import time

CODE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CODE_DIR)

from config.settings import Settings  # noqa: E402
from core import Robot  # noqa: E402
from hal import is_raspberry_pi, sim_requested  # noqa: E402

log = logging.getLogger("robot")


def main():
    parser = argparse.ArgumentParser(description="Humanoid Robot controller")
    parser.add_argument("--sim", action="store_true", help="run with simulated hardware")
    parser.add_argument("--host", default=None, help="web server address (default 0.0.0.0)")
    parser.add_argument("--port", type=int, default=None, help="web server port (default 80, simulator 8080)")
    parser.add_argument("--debug", action="store_true", help="more detailed log output")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    sim = args.sim or sim_requested()
    if not sim and not is_raspberry_pi():
        log.warning("Not running on a Raspberry Pi: switching to simulator mode")
        sim = True

    data_dir = os.environ.get("ROBOT_DATA_DIR") or (
        os.path.join(CODE_DIR, "sim_data") if sim else "/var/lib/humanoid-robot")
    settings = Settings(data_dir)
    web_cfg = settings.section("web")
    host = args.host or os.environ.get("ROBOT_HOST") or web_cfg["host"]
    port = args.port or int(os.environ.get("ROBOT_PORT", "0")) or (8080 if sim else int(web_cfg["port"]))

    robot = Robot(settings, sim=sim)
    robot.start()
    try:
        try:
            from control.web_server import run_server
        except ImportError as exc:
            # The robot keeps monitoring and alarming even without the web controller.
            log.error("Web controller unavailable (%s). Install python3-aiohttp.", exc)
            while True:
                time.sleep(3600)
        run_server(robot, host, port)
    except KeyboardInterrupt:
        pass
    finally:
        robot.stop()


if __name__ == "__main__":
    main()
