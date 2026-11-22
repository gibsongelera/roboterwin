/* Touch / mouse joystick. Reports x (right +) and y (forward +) in -1..1. */
(function () {
  "use strict";

  function Joystick(base, knob, options) {
    this.base = base;
    this.knob = knob;
    this.onMove = options.onMove || function () {};
    this.onEnd = options.onEnd || function () {};
    this.pointerId = null;
    var self = this;

    base.addEventListener("pointerdown", function (e) {
      if (self.pointerId !== null) return;
      self.pointerId = e.pointerId;
      try { base.setPointerCapture(e.pointerId); } catch (err) { /* older browsers */ }
      base.classList.add("active");
      self.update(e);
      e.preventDefault();
    });
    base.addEventListener("pointermove", function (e) {
      if (e.pointerId === self.pointerId) self.update(e);
    });
    var end = function (e) {
      if (e.pointerId !== self.pointerId) return;
      self.pointerId = null;
      base.classList.remove("active");
      knob.style.transform = "translate(0px, 0px)";
      self.onEnd();
    };
    base.addEventListener("pointerup", end);
    base.addEventListener("pointercancel", end);
    base.addEventListener("lostpointercapture", end);
  }

  Joystick.prototype.update = function (e) {
    var rect = this.base.getBoundingClientRect();
    var radius = rect.width / 2 - this.knob.offsetWidth / 2;
    var dx = e.clientX - (rect.left + rect.width / 2);
    var dy = e.clientY - (rect.top + rect.height / 2);
    var dist = Math.sqrt(dx * dx + dy * dy);
    if (dist > radius) {
      dx = dx * radius / dist;
      dy = dy * radius / dist;
    }
    this.knob.style.transform = "translate(" + dx + "px, " + dy + "px)";
    this.onMove(dx / radius, -dy / radius);
  };

  window.Joystick = Joystick;
})();
