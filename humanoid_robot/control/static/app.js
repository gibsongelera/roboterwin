/* Humanoid Robot phone controller.
 * Sends commands over a WebSocket and shows the status the robot pushes back.
 * While the joystick (or a direction button / key) is held, a "drive" command
 * is sent every 100 ms; the robot stops by itself 0.5 s after the last one.
 */
(function () {
  "use strict";

  var $ = function (id) { return document.getElementById(id); };
  var ws = null;
  var retries = 0;
  var lastStatus = null;
  var drive = { x: 0, y: 0, timer: null };
  var DEADZONE = 0.2;

  // ------------------------------------------------------------ connection
  function connect() {
    var proto = location.protocol === "https:" ? "wss://" : "ws://";
    ws = new WebSocket(proto + location.host + "/ws");
    ws.onopen = function () { retries = 0; setConnected(true); };
    ws.onclose = function () {
      setConnected(false);
      stopDriveTimer();
      setTimeout(connect, Math.min(3000, 400 * ++retries));
    };
    ws.onmessage = function (event) {
      var msg;
      try { msg = JSON.parse(event.data); } catch (e) { return; }
      if (msg.t === "status") render(msg.data);
      else if (msg.t === "error") toast(msg.msg);
    };
  }

  function send(obj) {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj));
  }

  function setConnected(on) {
    $("conn").classList.toggle("on", on);
    $("conn").title = on ? "Connected" : "Not connected";
    if (!on) {
      var state = $("state");
      state.className = "badge state-STARTING";
      state.textContent = "OFFLINE";
    }
  }

  // ------------------------------------------------------------ driving
  function describe(x, y) {
    var mag = Math.min(1, Math.sqrt(x * x + y * y));
    if (mag < DEADZONE) return "STOPPED";
    var pct = Math.round(30 + 70 * (mag - DEADZONE) / (1 - DEADZONE)) + "%";
    if (Math.abs(y) >= Math.abs(x)) return (y > 0 ? "FORWARD " : "BACKWARD ") + pct;
    return (x > 0 ? "TURN RIGHT " : "TURN LEFT ") + pct;
  }

  function setDrive(x, y) {
    drive.x = x;
    drive.y = y;
    $("drive-readout").textContent = describe(x, y);
    if (!drive.timer) {
      send({ t: "drive", x: x, y: y });
      drive.timer = setInterval(function () { send({ t: "drive", x: drive.x, y: drive.y }); }, 100);
    }
  }

  function stopDriveTimer() {
    if (drive.timer) { clearInterval(drive.timer); drive.timer = null; }
  }

  function endDrive() {
    stopDriveTimer();
    drive.x = drive.y = 0;
    $("drive-readout").textContent = "STOPPED";
    send({ t: "stop" });
  }

  new window.Joystick($("joystick"), $("knob"), { onMove: setDrive, onEnd: endDrive });

  Array.prototype.forEach.call(document.querySelectorAll("[data-drive]"), function (btn) {
    var xy = btn.getAttribute("data-drive").split(",").map(Number);
    btn.addEventListener("pointerdown", function (e) {
      try { btn.setPointerCapture(e.pointerId); } catch (err) { /* older browsers */ }
      btn.classList.add("held");
      setDrive(xy[0], xy[1]);
      e.preventDefault();
    });
    var release = function () {
      if (!btn.classList.contains("held")) return;
      btn.classList.remove("held");
      endDrive();
    };
    btn.addEventListener("pointerup", release);
    btn.addEventListener("pointercancel", release);
    btn.addEventListener("lostpointercapture", release);
  });
  $("stop").addEventListener("click", endDrive);

  // Keyboard control (desktop / tablet with keyboard)
  var keys = {};
  var KEYMAP = { ArrowUp: [0, 1], KeyW: [0, 1], ArrowDown: [0, -1], KeyS: [0, -1],
                 ArrowLeft: [-1, 0], KeyA: [-1, 0], ArrowRight: [1, 0], KeyD: [1, 0] };
  function keyVector() {
    var x = 0, y = 0;
    Object.keys(keys).forEach(function (k) { x += KEYMAP[k][0]; y += KEYMAP[k][1]; });
    return [Math.max(-1, Math.min(1, x)), Math.max(-1, Math.min(1, y))];
  }
  document.addEventListener("keydown", function (e) {
    if (e.target.tagName === "INPUT") return;
    if (e.code === "Escape") { keys = {}; endDrive(); send({ t: "estop" }); return; }
    if (e.code === "Space") { keys = {}; endDrive(); e.preventDefault(); return; }
    if (!KEYMAP[e.code] || keys[e.code]) return;
    keys[e.code] = true;
    var v = keyVector();
    setDrive(v[0], v[1]);
    e.preventDefault();
  });
  document.addEventListener("keyup", function (e) {
    if (!KEYMAP[e.code]) return;
    delete keys[e.code];
    if (Object.keys(keys).length === 0) endDrive();
    else { var v = keyVector(); setDrive(v[0], v[1]); }
  });

  // Phone locked / tab hidden / window lost focus -> stop
  document.addEventListener("visibilitychange", function () { if (document.hidden) { keys = {}; endDrive(); } });
  window.addEventListener("blur", function () { if (drive.timer) { keys = {}; endDrive(); } });

  // ------------------------------------------------------------ other controls
  $("estop").addEventListener("click", function () { endDrive(); send({ t: "estop" }); });
  $("reset").addEventListener("click", function () { send({ t: "reset" }); });
  $("silence").addEventListener("click", function () { send({ t: "silence" }); });

  Array.prototype.forEach.call(document.querySelectorAll("[data-mode]"), function (btn) {
    btn.addEventListener("click", function () { send({ t: "mode", mode: btn.getAttribute("data-mode") }); });
  });
  Array.prototype.forEach.call(document.querySelectorAll("[data-gesture]"), function (btn) {
    btn.addEventListener("click", function () { send({ t: "gesture", name: btn.getAttribute("data-gesture") }); });
  });
  Array.prototype.forEach.call(document.querySelectorAll("[data-say]"), function (btn) {
    btn.addEventListener("click", function () { send({ t: "say", text: btn.getAttribute("data-say") }); });
  });
  $("say-form").addEventListener("submit", function (e) {
    e.preventDefault();
    var text = $("say-text").value.trim();
    if (text) { send({ t: "say", text: text }); $("say-text").value = ""; }
  });

  var headTimer = null;
  $("head").addEventListener("input", function () {
    if (headTimer) return;
    headTimer = setTimeout(function () {
      headTimer = null;
      send({ t: "head", pos: -parseFloat($("head").value) });  // slider right = robot's right
    }, 80);
  });
  $("head-center").addEventListener("click", function () { $("head").value = 0; send({ t: "head", pos: 0 }); });

  // Video: only streams while switched on, to save Wi-Fi bandwidth and battery
  var videoOn = false;
  function setVideo(on) {
    videoOn = on;
    var img = $("video");
    if (on) {
      img.src = "/stream.mjpg?t=" + Date.now();
      $("video-off").textContent = "Connecting to camera...";
    } else {
      img.removeAttribute("src");
      $("video-off").textContent = 'Video is off. Tap "Start video".';
    }
    $("video-off").classList.remove("hidden");
    $("video-toggle").textContent = on ? "Stop video" : "Start video";
  }
  $("video").addEventListener("load", function () { $("video-off").classList.add("hidden"); });
  $("video").addEventListener("error", function () {
    if (!videoOn) return;
    $("video-off").classList.remove("hidden");
    $("video-off").textContent = "Camera offline" + (lastStatus ? ": " + lastStatus.camera.message : "");
  });
  $("video-toggle").addEventListener("click", function () { setVideo(!videoOn); });

  // ------------------------------------------------------------ rendering
  function fmt(value, digits, unit) {
    return value === null || value === undefined ? "--" : value.toFixed(digits) + unit;
  }

  function tile(id, value, sub, level, barPct) {
    var el = $(id);
    el.querySelector(".value").textContent = value;
    el.querySelector(".sub").textContent = sub || "";
    el.className = "tile" + (level ? " " + level : "");
    var bar = el.querySelector(".bar");
    if (bar) {
      bar.className = "bar" + (level === "warn" || level === "danger" ? " " + level : "");
      bar.firstElementChild.style.width = Math.max(0, Math.min(100, barPct || 0)) + "%";
    }
  }

  /* Rebuild a <ul> only when its content changed. parts(item) -> [[className, text], ...] */
  function renderList(ul, items, parts) {
    var key = JSON.stringify(items);
    if (ul.getAttribute("data-key") === key) return;
    ul.setAttribute("data-key", key);
    ul.textContent = "";
    var rows = items.length ? items.map(parts) : [[["time", "nothing yet"]]];
    rows.forEach(function (row) {
      var li = document.createElement("li");
      row.forEach(function (part) {
        var span = document.createElement("span");
        span.className = part[0];
        span.textContent = part[1];
        li.appendChild(span);
      });
      ul.appendChild(li);
    });
  }

  function render(s) {
    lastStatus = s;
    document.title = s.name + " - " + s.state;
    $("robot-name").textContent = s.name;

    var state = $("state");
    state.textContent = s.ready ? s.state : "STARTING";
    state.className = "badge state-" + (s.ready ? s.state : "STARTING");

    var bat = $("battery");
    var sens = s.sensors;
    if (sens.battery_pct === null) { bat.textContent = "BAT n/a"; bat.className = "badge"; }
    else {
      bat.textContent = "BAT " + sens.battery_pct + "%";
      bat.className = "badge " + (sens.battery_level === "ok" ? "ok" : sens.battery_level === "low" ? "warn" : "danger");
    }
    var sd = $("sd");
    sd.textContent = s.health.protected ? "SD PROTECTED" : "SD WRITABLE";
    sd.className = "badge " + (s.health.protected ? "ok" : "warn");
    sd.title = s.health.protected ? "Power can be cut safely" : "Maintenance mode: shut down before switching off";

    // Banner: emergency stop, dangers, warnings, power problems
    var banner = $("banner"), text = "", warnOnly = true;
    var dangers = s.hazards.filter(function (h) { return h.level === "danger"; });
    if (s.system_action) { text = "System " + s.system_action + " in progress..."; }
    else if (s.estop) { text = "EMERGENCY STOP is on. Release it when safe."; warnOnly = false; }
    else if (dangers.length) { text = "DANGER: " + dangers.map(function (h) { return h.text; }).join(", "); warnOnly = false; }
    else if (s.hazards.length) { text = s.hazards.map(function (h) { return h.text; }).join(", "); }
    else if (s.health.undervoltage_now) { text = "Power supply too weak (under-voltage)! Check the 5 V supply."; }
    if (text && s.silenced_s > 0 && !s.estop) text += " (sound silenced " + s.silenced_s + " s)";
    banner.classList.toggle("hidden", !text);
    banner.classList.toggle("warn", warnOnly);
    $("banner-text").textContent = text;
    $("silence").classList.toggle("hidden", !s.hazards.length || s.estop);
    $("silence").textContent = dangers.length ? "Silence / acknowledge" : "Silence";

    $("estop").classList.toggle("latched", s.estop);
    $("reset").classList.toggle("hidden", !s.estop);
    $("note").textContent = s.note || (s.activity !== "idle" ? "Activity: " + s.activity : "");

    if (!drive.timer) {
      $("drive-readout").textContent = s.motion === "stop" || s.motion === "freeze" ? "STOPPED" : s.motion.toUpperCase();
    }
    Array.prototype.forEach.call(document.querySelectorAll("[data-mode]"), function (btn) {
      btn.classList.toggle("active", btn.getAttribute("data-mode") === s.mode);
    });

    // Sensor tiles
    if (!sens.distance_ok) tile("t-distance", "--", "sensor not responding", "fault");
    else tile("t-distance", fmt(sens.distance_cm, 0, " cm"), s.state === "OBSTACLE" ? "obstacle!" : "",
              s.state === "OBSTACLE" ? "warn" : "");
    var heat = s.hazards.filter(function (h) { return h.key === "heat"; })[0];
    tile("t-temp", sens.dht_ok ? fmt(sens.temp_c, 1, " °C") : "--", sens.dht_ok ? "" : "no reading",
         heat ? (heat.level === "danger" ? "danger" : "warn") : (sens.dht_ok ? "" : "fault"));
    tile("t-hum", sens.dht_ok ? fmt(sens.humidity, 0, " %") : "--", "", sens.dht_ok ? "" : "fault");
    var gasLevel = sens.gas_level;
    var gasSub = { warmup: "warming up " + sens.gas_warmup_left + " s", normal: "normal", warning: "possible smoke/gas",
                   danger: "SMOKE / GAS!", absent: "sensor not connected", error: "ADC error" }[gasLevel] || gasLevel;
    tile("t-gas", fmt(sens.gas_v, 2, " V"), gasSub,
         gasLevel === "danger" ? "danger" : gasLevel === "warning" ? "warn" : (gasLevel === "absent" || gasLevel === "error") ? "fault" : "",
         sens.gas_v === null ? 0 : sens.gas_v / 5 * 100);
    if (sens.battery_pct === null) tile("t-bat", "--", "no battery (bench power)", "fault", 0);
    else tile("t-bat", sens.battery_pct + " %",
              fmt(sens.battery_v, 1, " V") + (sens.shutdown_in !== null ? " - shutdown in " + Math.round(sens.shutdown_in) + " s" : ""),
              sens.battery_level === "ok" ? "" : sens.battery_level === "low" ? "warn" : "danger", sens.battery_pct);
    var h = s.health;
    tile("t-cpu", fmt(h.cpu_temp_c, 0, " °C"),
         h.undervoltage_now ? "UNDER-VOLTAGE!" : h.undervoltage_seen ? "under-voltage happened" : "power OK",
         h.undervoltage_now ? "danger" : h.undervoltage_seen ? "warn" : "");

    $("last-said").textContent = s.speech.last || "-";
    renderList($("events"), s.events, function (e) { return [["time", e.t], ["", e.text]]; });
    var checks = Object.keys(s.checks).map(function (k) { return s.checks[k]; });
    renderList($("checks"), checks, function (c) {
      return [[c.ok ? "ok" : "bad", c.ok ? "OK" : "FAIL"], ["", c.label + " - " + c.msg]];
    });

    if (s.sim) initSim();
  }

  var toastTimer = null;
  function toast(text) {
    var el = $("toast");
    el.textContent = text;
    el.classList.remove("hidden");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.classList.add("hidden"); }, 2500);
  }

  // ------------------------------------------------------------ simulator card
  var simReady = false;
  function initSim() {
    if (simReady) return;
    simReady = true;
    $("sim-card").classList.remove("hidden");
    var fields = { "sim-distance": "distance_cm", "sim-temp": "temp_c", "sim-gas": "gas_sensor_v", "sim-bat": "battery_v" };
    fetch("/api/sim").then(function (r) { return r.json(); }).then(function (world) {
      Object.keys(fields).forEach(function (id) {
        var input = $(id);
        input.value = world[fields[id]];
        $(id + "-v").textContent = input.value;
        input.addEventListener("input", function () {
          $(id + "-v").textContent = input.value;
          var patch = {};
          patch[fields[id]] = parseFloat(input.value);
          postSim(patch);
        });
      });
      $("sim-protected").checked = world.protected;
      $("sim-uv").checked = world.undervoltage;
      $("sim-protected").addEventListener("change", function () { postSim({ protected: $("sim-protected").checked }); });
      $("sim-uv").addEventListener("change", function () { postSim({ undervoltage: $("sim-uv").checked }); });
    });
  }
  function postSim(patch) {
    fetch("/api/sim", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch) });
  }

  connect();
})();
