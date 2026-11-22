"""End-to-end test of the web controller with the simulated robot."""

import asyncio
import time

import pytest

aiohttp = pytest.importorskip("aiohttp")
from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

from config.settings import Settings  # noqa: E402
from control.web_server import create_app  # noqa: E402
from core import Robot  # noqa: E402


async def _wait(predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.05)
    return predicate()


def test_drive_disconnect_estop_and_save(tmp_path):
    async def scenario():
        robot = Robot(Settings(str(tmp_path)), sim=True)
        robot.start()
        assert await _wait(lambda: robot.ready, 15)
        client = TestClient(TestServer(create_app(robot)))
        await client.start_server()
        try:
            status = await (await client.get("/api/status")).json()
            assert status["sim"] is True and status["checks"]["servos"]["ok"]

            ws = await client.ws_connect("/ws")
            assert (await ws.receive_json())["t"] == "status"

            await ws.send_json({"t": "drive", "x": 0, "y": 1})
            assert await _wait(lambda: robot.decision.motion == "forward", 0.4)

            # obstacle in front blocks forward walking
            robot.hw.world.update({"distance_cm": 10})
            await ws.send_json({"t": "drive", "x": 0, "y": 1})
            assert await _wait(lambda: robot.decision.state == "OBSTACLE", 1.0)
            robot.hw.world.update({"distance_cm": 150})

            # closing the phone's connection stops the robot at once
            await ws.send_json({"t": "drive", "x": 0, "y": 1})
            await ws.close()
            assert await _wait(lambda: robot.decision.motion == "stop", 0.4)

            ws = await client.ws_connect("/ws")
            await ws.send_json({"t": "estop"})
            assert await _wait(lambda: robot.decision.state == "STOPPED", 1.0)
            await ws.send_json({"t": "drive", "x": 0, "y": 1})
            await asyncio.sleep(0.3)
            assert robot.decision.motion == "freeze"
            await ws.send_json({"t": "reset"})
            assert await _wait(lambda: robot.decision.state == "READY", 1.0)
            await ws.close()

            r = await client.post("/api/settings", json={"patch": {"thresholds": {"obstacle_stop_cm": 30}}, "save": True})
            assert (await r.json())["persisted"] is True
            robot.hw.world.update({"protected": True})
            r = await client.post("/api/settings", json={"patch": {}, "save": True})
            assert (await r.json())["persisted"] is False

            r = await client.get("/stream.mjpg")
            assert r.status == 503  # no camera in the simulator
        finally:
            await client.close()
            robot.stop()

    asyncio.run(scenario())
