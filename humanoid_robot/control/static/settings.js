/* Settings page: servo calibration, thresholds, saving and SD card protection. */
(function () {
  "use strict";

  var $ = function (id) { return document.getElementById(id); };
  var ws = null;
  var settings = null;

  var THRESHOLDS = [
    ["obstacle_stop_cm", "Stop when obstacle closer than (cm)"],
    ["obstacle_clear_cm", "Path clear again at (cm)"],
    ["temp_warning_c", "Temperature warning (°C)"],
    ["temp_danger_c", "Temperature EMERGENCY (°C)"],
    ["gas_warmup_s", "MQ-2 warm-up time (s)"],
    ["gas_warning_rise_v", "Gas warning: rise above clean air (V)"],
    ["gas_danger_rise_v", "Gas EMERGENCY: rise above clean air (V)"],
    ["gas_danger_absolute_v", "Gas EMERGENCY: MQ-2 voltage above (V)"],
    ["battery_warning_v", "Battery low warning (V)"],
    ["battery_shutdown_v", "Battery safe shutdown (V)"],
    ["battery_shutdown_delay_s", "Shutdown after low voltage for (s)"],
    ["silence_s", "Silence button lasts (s)"]
  ];
  var MOTION = [
    ["step_ms", "Time per gait step (ms)"],
    ["home_transition_ms", "Return to home pose (ms)"],
    ["max_speed_deg_per_s", "Servo speed limit (deg/s)"],
    ["head_range_deg", "Head turn range (deg)"],
    ["auto_speed", "Auto patrol speed (0-1)"],
    ["watchdog_ms", "Stop if phone silent for (ms)"]
  ];

  function connect() {
    ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws");
    ws.onopen = function () { $("conn").classList.add("on"); };
    ws.onclose = function () { $("conn").classList.remove("on"); setTimeout(connect, 1500); };
    ws.onmessage = function (event) {
      var msg;
      try { msg = JSON.parse(event.data); } catch (e) { return; }
      if (msg.t === "status") renderStatus(msg.data);
      else if (msg.t === "error") toast(msg.msg);
    };
  }
  function send(obj) { if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj)); }

  function el(tag, attrs, text) {
    var node = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) { node.setAttribute(k, attrs[k]); });
    if (text !== undefined) node.textContent = text;
    return node;
  }

  // ------------------------------------------------------------ build forms
  function buildServoRows() {
    var body = $("servo-rows");
    body.textContent = "";
    Object.keys(settings.servos).forEach(function (name) {
      var cfg = settings.servos[name];
      var tr = el("tr", { "data-joint": name });
      tr.appendChild(el("td", { "class": "servo-row-name" }, name));
      tr.appendChild(el("td", {}, String(cfg.channel)));
      tr.appendChild(el("td", { "class": "angle" }, "--"));

      var trimCell = el("td", { "class": "trim-cell" });
      var trim = el("input", { type: "range", min: "-30", max: "30", step: "1", value: String(cfg.trim),
                               "aria-label": name + " trim" });
      var trimValue = el("span", {}, " " + cfg.trim + "°");
      var timer = null;
      trim.addEventListener("input", function () {
        trimValue.textContent = " " + trim.value + "°";
        cfg.trim = parseFloat(trim.value);
        if (timer) return;
        timer = setTimeout(function () { timer = null; send({ t: "trim", joint: name, value: cfg.trim }); }, 100);
      });
      trimCell.appendChild(trim);
      trimCell.appendChild(trimValue);
      tr.appendChild(trimCell);

      var testCell = el("td");
      [-15, 15].forEach(function (offset) {
        var b = el("button", { "class": "small", type: "button" }, (offset > 0 ? "+" : "") + offset + "°");
        b.addEventListener("click", function () { send({ t: "test_servo", joint: name, offset: offset }); });
        testCell.appendChild(b);
        testCell.appendChild(document.createTextNode(" "));
      });
      tr.appendChild(testCell);

      var invCell = el("td");
      var inv = el("input", { type: "checkbox", "aria-label": name + " invert" });
      inv.checked = cfg.invert;
      inv.addEventListener("change", function () { cfg.invert = inv.checked; apply(false); });
      invCell.appendChild(inv);
      tr.appendChild(invCell);

      ["min", "max"].forEach(function (key) {
        var cell = el("td");
        var input = el("input", { type: "number", min: "0", max: "180", step: "1", value: String(cfg[key]),
                                  "aria-label": name + " " + key });
        input.addEventListener("change", function () { cfg[key] = parseFloat(input.value); });
        cell.appendChild(input);
        tr.appendChild(cell);
      });
      body.appendChild(tr);
    });
  }

  function buildNumberForm(containerId, section, fields) {
    var box = $(containerId);
    box.textContent = "";
    fields.forEach(function (f) {
      var label = el("label", {}, f[1]);
      var input = el("input", { type: "number", step: "any", value: String(settings[section][f[0]]) });
      input.addEventListener("change", function () { settings[section][f[0]] = parseFloat(input.value); });
      label.appendChild(input);
      box.appendChild(label);
    });
  }

  function load() {
    fetch("/api/settings").then(function (r) { return r.json(); }).then(function (data) {
      settings = data;
      buildServoRows();
      buildNumberForm("thresholds", "thresholds", THRESHOLDS);
      buildNumberForm("motion", "motion", MOTION);
      $("source").textContent = data.source;
    });
  }

  // ------------------------------------------------------------ save / apply
  function patch() {
    var servos = {};
    Object.keys(settings.servos).forEach(function (name) {
      var c = settings.servos[name];
      servos[name] = { trim: c.trim, invert: c.invert, min: c.min, max: c.max };
    });
    return { servos: servos, thresholds: settings.thresholds, motion: settings.motion };
  }

  function apply(save) {
    fetch("/api/settings", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ patch: patch(), save: save })
    }).then(function (r) { return r.json(); }).then(function (res) {
      $("save-result").textContent = res.message;
      if (save) toast(res.persisted ? "Saved permanently" : "Not saved permanently - see message");
      load();
    });
  }
  $("btn-apply").addEventListener("click", function () { apply(false); });
  $("btn-save").addEventListener("click", function () { apply(true); });

  $("btn-hold").addEventListener("click", function () { send({ t: "servos", on: true }); });
  $("btn-relax").addEventListener("click", function () {
    if (confirm("Relax all servos? A standing robot WILL FALL. Hold it or put it on a stand first.")) {
      send({ t: "servos", on: false });
    }
  });

  // ------------------------------------------------------------ system actions
  function system(action, question) {
    if (!confirm(question)) return;
    fetch("/api/system", { method: "POST", headers: { "Content-Type": "application/json" },
                           body: JSON.stringify({ action: action }) })
      .then(function (r) { return r.json(); })
      .then(function (res) { $("power-info").textContent = res.message; toast(res.message); });
  }
  $("btn-maintenance").addEventListener("click", function () {
    system("maintenance", "Switch to MAINTENANCE mode? The robot reboots and the SD card becomes writable. " +
           "Always use 'Shut down' before switching power off in this mode.");
  });
  $("btn-protect").addEventListener("click", function () {
    system("protect", "Switch to PROTECTED mode? The robot reboots and the SD card becomes read-only " +
           "(power can then be cut at any time).");
  });
  $("btn-reboot").addEventListener("click", function () { system("reboot", "Reboot the robot now?"); });
  $("btn-shutdown").addEventListener("click", function () {
    system("shutdown", "Shut down the robot? It crouches, then the Raspberry Pi turns off. " +
           "Switch the main power off afterwards.");
  });

  // ------------------------------------------------------------ status
  function renderStatus(s) {
    $("state").textContent = s.state;
    $("state").className = "badge state-" + s.state;
    var prot = s.health.protected;
    $("sd").textContent = prot ? "SD PROTECTED" : "SD WRITABLE";
    $("sd").className = "badge " + (prot ? "ok" : "warn");
    var info = $("sd-info");
    if (prot) {
      info.className = "callout ok";
      info.textContent = "PROTECTED mode: the SD card is read-only. Power can be switched off at any moment " +
        "without damaging it. Changes (settings, files) are kept in RAM and lost at reboot. " +
        "To save calibration permanently, switch to Maintenance mode, save, then switch back.";
    } else {
      info.className = "callout warn";
      info.textContent = "MAINTENANCE mode: the SD card is writable. Save your settings now, then switch " +
        "back to Protected mode. In this mode ALWAYS use 'Shut down' and wait before switching power off.";
    }
    $("btn-maintenance").classList.toggle("hidden", !prot);
    $("btn-protect").classList.toggle("hidden", prot);
    $("save-hint").textContent = prot
      ? "Protected mode: 'Save permanently' keeps changes only until the next reboot."
      : "Maintenance mode: 'Save permanently' writes to the SD card.";
    $("save-hint").className = "callout " + (prot ? "warn" : "ok");

    var angles = (s.servos && s.servos.angles) || {};
    Array.prototype.forEach.call(document.querySelectorAll("#servo-rows tr"), function (tr) {
      var a = angles[tr.getAttribute("data-joint")];
      tr.querySelector(".angle").textContent = a === undefined ? "--" : a.toFixed(0) + "°";
    });
    $("btn-hold").textContent = s.servos.enabled ? "Hold servos (home pose)" : "Enable servos (home pose)";

    var list = $("checks");
    var key = JSON.stringify(s.checks);
    if (list.getAttribute("data-key") !== key) {
      list.setAttribute("data-key", key);
      list.textContent = "";
      Object.keys(s.checks).forEach(function (k) {
        var c = s.checks[k];
        var li = el("li");
        li.appendChild(el("span", { "class": c.ok ? "ok" : "bad" }, c.ok ? "OK" : "FAIL"));
        li.appendChild(el("span", {}, c.label + " - " + c.msg));
        list.appendChild(li);
      });
    }
  }

  var toastTimer = null;
  function toast(text) {
    var t = $("toast");
    t.textContent = text;
    t.classList.remove("hidden");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.classList.add("hidden"); }, 3000);
  }

  load();
  connect();
})();
