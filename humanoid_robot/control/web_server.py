"""Local web server for the phone controller (works without internet).

  GET  /                 joystick dashboard        (static/index.html)
  GET  /settings         calibration + system page (static/settings.html)
  GET  /ws               WebSocket: commands up, status down (5 per second)
  GET  /stream.mjpg      live camera (MJPEG)
  GET  /api/status       status JSON
  GET  /api/settings     servo table, thresholds and protection mode
  POST /api/settings     {"patch": {...}, "save": true|false}
  POST /api/system       {"action": "shutdown|reboot|maintenance|protect"}
  GET/POST /api/sim      simulator values (only when running with --sim)

Safety: if the WebSocket of the phone that is driving closes, the robot stops
immediately; if it stays open but stops sending, the 0.5 s watchdog in
safety/state_machine.py stops the robot.
"""

import asyncio
import itertools
import json
import logging
import os

from aiohttp import WSMsgType, web

log = logging.getLogger(__name__)

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
STATUS_PERIOD_S = 0.2
_client_ids = itertools.count(1)

# web.AppKey exists from aiohttp 3.9; Raspberry Pi OS Bookworm ships 3.8.
_AppKey = getattr(web, "AppKey", None)
ROBOT_KEY = _AppKey("robot", object) if _AppKey else "robot"
CLIENTS_KEY = _AppKey("clients", set) if _AppKey else "clients"


def _num(value, default=0.0, low=-1.0, high=1.0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number:  # NaN
        return default
    return max(low, min(high, number))


def handle_command(robot, client_id, msg):
    """Execute one WebSocket command. Returns an error text or None."""
    kind = msg.get("t")
    if kind == "drive":
        return robot.drive(client_id, _num(msg.get("x")), _num(msg.get("y")))
    if kind == "stop":
        robot.stop_drive()
    elif kind == "estop":
        robot.estop("phone")
    elif kind == "reset":
        if not robot.reset_estop():
            return "Emergency stop was not active"
    elif kind == "mode":
        if not robot.set_mode(str(msg.get("mode"))):
            return "Unknown mode"
    elif kind == "head":
        robot.set_head(_num(msg.get("pos")))
    elif kind == "gesture":
        return robot.gesture(str(msg.get("name", "")))
    elif kind == "say":
        robot.speak_text(msg.get("text", ""))
    elif kind == "silence":
        robot.silence()
    elif kind == "trim":
        return robot.set_trim(str(msg.get("joint")), _num(msg.get("value"), 0.0, -30.0, 30.0))
    elif kind == "test_servo":
        return robot.test_servo(str(msg.get("joint")), _num(msg.get("offset"), 0.0, -45.0, 45.0))
    elif kind == "servos":
        return robot.servos_power(bool(msg.get("on")))
    elif kind == "ping":
        pass
    else:
        return "Unknown command"
    return None


async def ws_handler(request):
    robot = request.app[ROBOT_KEY]
    ws = web.WebSocketResponse(heartbeat=2.0)
    await ws.prepare(request)
    client_id = next(_client_ids)
    request.app[CLIENTS_KEY].add(ws)
    log.info("Phone %d connected from %s", client_id, request.remote)
    try:
        await ws.send_json({"t": "status", "data": robot.status()})
        async for message in ws:
            if message.type != WSMsgType.TEXT:
                continue
            try:
                data = json.loads(message.data)
                if not isinstance(data, dict):
                    raise ValueError("not an object")
            except ValueError:
                await ws.send_json({"t": "error", "msg": "bad message"})
                continue
            error = handle_command(robot, client_id, data)
            if error:
                await ws.send_json({"t": "error", "msg": error})
    finally:
        request.app[CLIENTS_KEY].discard(ws)
        robot.client_disconnected(client_id)
        log.info("Phone %d disconnected", client_id)
    return ws


async def broadcast_status(app):
    robot = app[ROBOT_KEY]
    while True:
        await asyncio.sleep(STATUS_PERIOD_S)
        if not app[CLIENTS_KEY]:
            continue
        payload = json.dumps({"t": "status", "data": robot.status()})
        for ws in list(app[CLIENTS_KEY]):
            try:
                await ws.send_str(payload)
            except (ConnectionResetError, RuntimeError):
                app[CLIENTS_KEY].discard(ws)


async def background_tasks(app):
    task = asyncio.create_task(broadcast_status(app))
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def stream_handler(request):
    camera = request.app[ROBOT_KEY].camera
    loop = asyncio.get_running_loop()
    if not camera.available or not await loop.run_in_executor(None, camera.acquire):
        return web.Response(status=503, text="camera offline")
    response = web.StreamResponse(headers={
        "Content-Type": "multipart/x-mixed-replace; boundary=FRAME",
        "Cache-Control": "no-cache, private", "Pragma": "no-cache"})
    try:
        await response.prepare(request)
        last_id = -1
        while True:
            frame, last_id = await loop.run_in_executor(None, camera.buffer.wait_frame, last_id, 1.0)
            if frame is None:
                continue
            await response.write(b"--FRAME\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                 + str(len(frame)).encode() + b"\r\n\r\n" + frame + b"\r\n")
    except (ConnectionResetError, asyncio.CancelledError):
        pass
    finally:
        camera.release()
    return response


async def status_handler(request):
    return web.json_response(request.app[ROBOT_KEY].status())


async def settings_get(request):
    robot = request.app[ROBOT_KEY]
    s = robot.settings.snapshot()
    return web.json_response({
        "servos": s["servos"], "thresholds": s["thresholds"], "motion": s["motion"],
        "calibration": s["calibration"], "audio": s["audio"],
        "protected": robot.health.protected(), "source": robot.settings.source,
    })


async def settings_post(request):
    robot = request.app[ROBOT_KEY]
    try:
        body = await request.json()
    except ValueError:
        return web.json_response({"ok": False, "message": "bad JSON"}, status=400)
    patch = body.get("patch") if isinstance(body, dict) else None
    if not isinstance(patch, dict):
        return web.json_response({"ok": False, "message": "missing patch"}, status=400)
    allowed = {k: v for k, v in patch.items() if k in ("servos", "thresholds", "motion", "calibration", "audio")}
    result = robot.update_settings(allowed, save=bool(body.get("save")))
    result["ok"] = True
    return web.json_response(result)


async def system_post(request):
    try:
        body = await request.json()
    except ValueError:
        body = {}
    action = body.get("action") if isinstance(body, dict) else None
    return web.json_response(request.app[ROBOT_KEY].system_action(str(action)))


async def sim_get(request):
    return web.json_response(request.app[ROBOT_KEY].hw.world.to_dict())


async def sim_post(request):
    try:
        body = await request.json()
    except ValueError:
        body = {}
    return web.json_response(request.app[ROBOT_KEY].hw.world.update(body if isinstance(body, dict) else {}))


def _page(name):
    path = os.path.join(STATIC_DIR, name)

    async def handler(_request):
        return web.FileResponse(path, headers={"Cache-Control": "no-cache"})
    return handler


async def _on_shutdown(app):
    for ws in list(app[CLIENTS_KEY]):
        await ws.close()


def create_app(robot):
    app = web.Application()
    app[ROBOT_KEY] = robot
    app[CLIENTS_KEY] = set()
    app.router.add_get("/", _page("index.html"))
    app.router.add_get("/settings", _page("settings.html"))
    app.router.add_get("/ws", ws_handler)
    app.router.add_get("/stream.mjpg", stream_handler)
    app.router.add_get("/api/status", status_handler)
    app.router.add_get("/api/settings", settings_get)
    app.router.add_post("/api/settings", settings_post)
    app.router.add_post("/api/system", system_post)
    if robot.hw.world is not None:
        app.router.add_get("/api/sim", sim_get)
        app.router.add_post("/api/sim", sim_post)
    app.router.add_static("/static/", STATIC_DIR)
    app.cleanup_ctx.append(background_tasks)
    app.on_shutdown.append(_on_shutdown)
    return app


def run_server(robot, host, port):
    log.info("Web controller on http://%s:%s", host, port)
    web.run_app(create_app(robot), host=host, port=port, access_log=None, print=None)
