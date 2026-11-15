/* Animated gesture demonstrations.
 *
 * Builds an inline-SVG hand (same geometry as the desktop app's illustrations) plus a small
 * "screen" scene for every gesture. All motion is done with CSS keyframes in animations.css;
 * the hand and the screen share one duration so they stay in sync.
 */
(function () {
  "use strict";

  // knuckle x, width, length, default angle
  var FINGERS = {
    index: [66, 21, 74, -6],
    middle: [90, 22, 84, -1],
    ring: [113, 21, 78, 4],
    pinky: [135, 18, 60, 10]
  };
  var THUMB = { x: 58, y: 160, w: 23, len: 72 };
  var KY = 126;
  var ORDER = ["pinky", "ring", "middle", "index"];

  function straight(name, angle, active) {
    var f = FINGERS[name], w = f[1], L = f[2];
    var fill = active ? "url(#hg-act)" : "url(#hg-skin)";
    return '<g transform="translate(' + f[0] + ' ' + KY + ')">' +
      '<g class="seg f-' + name + '" style="transform:rotate(' + (angle == null ? f[3] : angle) + 'deg)">' +
      '<rect x="' + (-w / 2) + '" y="' + (-L) + '" width="' + w + '" height="' + (L + 18) + '" rx="' + (w / 2) + '" fill="' + fill + '" class="hg-edge"/>' +
      '<rect x="' + (-w / 2 + 5) + '" y="' + (-L + 4) + '" width="' + (w - 10) + '" height="9" rx="4" class="hg-nail"/>' +
      '<line x1="' + (-w / 2 + 4) + '" x2="' + (w / 2 - 4) + '" y1="' + (-L * 0.45) + '" y2="' + (-L * 0.45) + '" class="hg-crease"/>' +
      (name === "index" ? '<circle class="tip tip-index" cx="0" cy="' + (-L + 5) + '" r="5"/>' : "") +
      (name !== "index" && active ? '<circle class="tip tip-other" cx="0" cy="' + (-L + 5) + '" r="4"/>' : "") +
      "</g></g>";
  }

  function curled(name) {
    var f = FINGERS[name], w = f[1];
    return '<g transform="translate(' + f[0] + ' ' + KY + ')"><g class="curl c-' + name + '">' +
      '<rect x="' + (-w / 2) + '" y="-20" width="' + w + '" height="44" rx="' + (w / 2) + '" fill="url(#hg-curl)" class="hg-edge"/>' +
      '<line x1="' + (-w / 2 + 4) + '" x2="' + (w / 2 - 4) + '" y1="2" y2="2" class="hg-crease"/></g></g>';
  }

  function thumb(angle, scale, active) {
    var fill = active ? "url(#hg-act)" : "url(#hg-skin)";
    return '<g transform="translate(' + THUMB.x + ' ' + THUMB.y + ')">' +
      '<g class="seg f-thumb" style="transform:rotate(' + angle + 'deg) scale(1,' + scale + ')">' +
      '<rect x="' + (-THUMB.w / 2) + '" y="' + (-THUMB.len) + '" width="' + THUMB.w + '" height="' + (THUMB.len + 22) + '" rx="' + (THUMB.w / 2) + '" fill="' + fill + '" class="hg-edge"/>' +
      '<rect x="' + (-THUMB.w / 2 + 5) + '" y="' + (-THUMB.len + 4) + '" width="' + (THUMB.w - 10) + '" height="9" rx="4" class="hg-nail"/>' +
      (active ? '<circle class="tip tip-thumb" cx="0" cy="' + (-THUMB.len + 5) + '" r="5"/>' : "") +
      "</g></g>";
  }

  var DEFS = '<defs>' +
    '<linearGradient id="hg-act" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#38d5f0"/><stop offset="1" stop-color="#8b7dff"/></linearGradient>' +
    '<linearGradient id="hg-skin" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="var(--hand-1)"/><stop offset="1" stop-color="var(--hand-2)"/></linearGradient>' +
    '<linearGradient id="hg-curl" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="var(--hand-1)"/><stop offset="1" stop-color="var(--hand-3)"/></linearGradient>' +
    '</defs>';

  /* cfg: { curled:[names], straight:{name:angle}, bend:{name:angle}, thumb:[angle, scale, front], active:[names], extra:svg } */
  function buildHand(cfg) {
    var active = cfg.active || [];
    var isActive = function (n) { return active.indexOf(n) >= 0; };
    var t = cfg.thumb || [38, 0.72, true];
    var out = [DEFS, '<g class="hand">'];
    out.push('<rect x="72" y="196" width="58" height="46" rx="14" fill="url(#hg-skin)" class="hg-edge"/>');
    if (!t[2]) out.push(thumb(t[0], t[1], isActive("thumb")));
    ORDER.forEach(function (n) {
      if (cfg.straight && n in cfg.straight) out.push(straight(n, cfg.straight[n], isActive(n)));
    });
    out.push('<rect x="50" y="116" width="100" height="96" rx="30" fill="url(#hg-skin)" class="hg-edge"/>');
    (cfg.curled || []).forEach(function (n) { out.push(curled(n)); });
    if (t[2]) out.push(thumb(t[0], t[1], isActive("thumb")));
    ORDER.forEach(function (n) {
      if (cfg.bend && n in cfg.bend) out.push(straight(n, cfg.bend[n], isActive(n)));
    });
    out.push(cfg.extra || "");
    out.push("</g>");
    return '<svg class="hand-svg" viewBox="-30 -20 260 270" role="img" aria-label="' + (cfg.label || "hand gesture") + '">' + out.join("") + "</svg>";
  }

  /* ---------------------------------------------------------------- screen scenes */
  var CURSOR = '<g class="cursor"><path d="M0 0 L0 17 L4.5 13 L8 21 L11 19.6 L7.6 12 L13.5 12 Z" class="cursor-path"/></g>';
  function screen(inner, label) {
    return '<svg class="screen-svg" viewBox="0 0 240 160" role="img" aria-label="' + label + '">' +
      '<rect width="240" height="160" rx="10" class="scr-bg"/>' +
      '<rect y="146" width="240" height="14" class="scr-taskbar"/>' +
      '<circle cx="14" cy="153" r="3.5" class="scr-start"/>' + inner + "</svg>";
  }
  function win(x, y, w, h, title, cls) {
    return '<g class="' + (cls || "") + '"><rect x="' + x + '" y="' + y + '" width="' + w + '" height="' + h + '" rx="5" class="scr-win"/>' +
      '<rect x="' + x + '" y="' + y + '" width="' + w + '" height="13" rx="5" class="scr-title"/>' +
      '<text x="' + (x + 7) + '" y="' + (y + 9.5) + '" class="scr-text">' + title + "</text>" +
      '<circle cx="' + (x + w - 8) + '" cy="' + (y + 6.5) + '" r="2.6" class="scr-close"/></g>';
  }
  function lines(x, y, n, w) {
    var s = "";
    for (var i = 0; i < n; i++) s += '<rect x="' + x + '" y="' + (y + i * 11) + '" width="' + (w - (i % 3) * 18) + '" height="5" rx="2.5" class="scr-line"/>';
    return s;
  }
  function icon(x, y, label, cls) {
    return '<g class="' + (cls || "") + '"><rect x="' + x + '" y="' + y + '" width="22" height="18" rx="3" class="scr-folder"/>' +
      '<rect x="' + x + '" y="' + (y - 3) + '" width="10" height="5" rx="2" class="scr-folder"/>' +
      '<text x="' + (x + 11) + '" y="' + (y + 28) + '" class="scr-text small" text-anchor="middle">' + label + "</text></g>";
  }
  function ring(cx, cy, r, cls) {
    var c = 2 * Math.PI * r;
    return '<circle cx="' + cx + '" cy="' + cy + '" r="' + r + '" class="ring-bg"/>' +
      '<circle cx="' + cx + '" cy="' + cy + '" r="' + r + '" class="ring ' + (cls || "") + '" style="stroke-dasharray:' + c + ';--c:' + c + '" transform="rotate(-90 ' + cx + " " + cy + ')"/>';
  }

  var PALM = ring(100, 160, 70, "palm-ring");

  var DEMOS = {
    move: {
      dur: 6,
      hand: { straight: { index: -6 }, curled: ["middle", "ring", "pinky"], active: ["index"], label: "Index finger pointing and moving" },
      scene: screen(win(26, 18, 120, 70, "Documents") + lines(36, 40, 4, 90) + icon(180, 30, "Photos") + CURSOR, "Cursor follows the finger")
    },
    click: {
      dur: 2.6,
      hand: { straight: {}, curled: ["middle", "ring", "pinky"], bend: { index: -6 }, thumb: [-35, 1, true], active: ["index", "thumb"], label: "Thumb and index pinch once" },
      scene: screen(win(30, 20, 180, 100, "Settings") + '<rect x="84" y="62" width="72" height="22" rx="11" class="scr-button"/><text x="120" y="76.5" class="scr-text" text-anchor="middle">OK</text>' +
        '<circle cx="118" cy="74" r="14" class="ripple"/>' + '<g class="cursor-at" style="transform:translate(116px,72px)">' + CURSOR + "</g>", "Button receives one click")
    },
    "double-click": {
      dur: 3,
      hand: { straight: {}, curled: ["middle", "ring", "pinky"], bend: { index: -6 }, thumb: [-35, 1, true], active: ["index", "thumb"], label: "Two quick thumb and index pinches" },
      scene: screen(icon(60, 40, "Projects", "dbl-icon") + icon(120, 40, "Music") + '<circle cx="71" cy="49" r="13" class="ripple r1"/><circle cx="71" cy="49" r="13" class="ripple r2"/>' +
        win(36, 30, 170, 100, "Projects", "dbl-window") + '<g class="dbl-window">' + lines(48, 56, 5, 120) + "</g>" +
        '<g class="cursor-at" style="transform:translate(70px,48px)">' + CURSOR + "</g>", "Folder opens with a double click")
    },
    "right-click": {
      dur: 2.8,
      hand: { straight: { index: -30 }, curled: ["ring", "pinky"], bend: { middle: -1 }, thumb: [-35, 1, true], active: ["middle", "thumb"], label: "Thumb and middle finger pinch" },
      scene: screen(icon(70, 50, "Report") + '<g class="ctx-menu"><rect x="92" y="58" width="82" height="66" rx="5" class="scr-menu"/>' +
        lines(100, 68, 5, 62) + "</g>" + '<g class="cursor-at" style="transform:translate(90px,56px)">' + CURSOR + "</g>", "Context menu opens")
    },
    "long-press": {
      dur: 3.6,
      hand: { straight: {}, curled: ["middle", "ring", "pinky"], bend: { index: -6 }, thumb: [-35, 1, true], active: ["index", "thumb"], label: "Hold the pinch",
        extra: '<g class="lp-ring">' + ring(48, 70, 30, "hold-ring") + "</g>" },
      scene: screen(win(30, 20, 180, 100, "Editor") + '<rect x="84" y="62" width="72" height="22" rx="11" class="scr-button lp-button"/>' +
        '<text x="120" y="76.5" class="scr-text" text-anchor="middle">Hold</text>' + '<g class="lp-screen-ring">' + ring(120, 73, 20, "hold-ring") + "</g>" +
        '<g class="cursor-at" style="transform:translate(116px,72px)">' + CURSOR + "</g>", "Button is held down")
    },
    drag: {
      dur: 5,
      hand: { straight: {}, curled: ["middle", "ring", "pinky"], bend: { index: -6 }, thumb: [-35, 1, true], active: ["index", "thumb"], label: "Pinch, move and release" },
      scene: screen('<g class="drop-target">' + icon(176, 56, "Archive") + "</g>" + '<g class="drag-file"><rect x="-10" y="-12" width="20" height="24" rx="3" class="scr-file"/>' +
        '<path d="M4 -12 L10 -6 L4 -6 Z" class="scr-fold"/><text x="0" y="22" class="scr-text small" text-anchor="middle">notes.txt</text>' +
        '<g transform="translate(2 2)">' + CURSOR + "</g></g>", "File dragged into a folder")
    },
    "scroll-vertical": {
      dur: 4,
      hand: { straight: { index: -3, middle: -1 }, curled: ["ring", "pinky"], active: ["index", "middle"], label: "Two fingers moving up and down" },
      scene: screen('<defs><clipPath id="clip-v"><rect x="40" y="33" width="160" height="92"/></clipPath></defs>' + win(30, 20, 180, 110, "Article") +
        '<g clip-path="url(#clip-v)"><g class="vscroll-content">' + lines(46, 38, 16, 140) + "</g></g>" +
        '<rect x="202" y="36" width="4" height="88" rx="2" class="scr-line"/><rect x="202" y="36" width="4" height="26" rx="2" class="scr-thumb vscroll-bar"/>', "Page scrolls")
    },
    "scroll-horizontal": {
      dur: 4,
      hand: { straight: { index: -3, middle: -1 }, curled: ["ring", "pinky"], active: ["index", "middle"], label: "Two fingers moving left and right" },
      scene: screen('<defs><clipPath id="clip-h"><rect x="36" y="34" width="168" height="90"/></clipPath></defs>' + win(30, 20, 180, 110, "Gallery") +
        '<g clip-path="url(#clip-h)"><g class="hscroll-content">' +
        [0, 1, 2, 3, 4, 5].map(function (i) { return '<rect x="' + (42 + i * 56) + '" y="44" width="48" height="66" rx="5" class="scr-card c' + (i % 3) + '"/>'; }).join("") +
        "</g></g>", "Content scrolls sideways")
    },
    "window-move": {
      dur: 5,
      hand: { straight: { index: -4, middle: -1, ring: 3 }, curled: ["pinky"], active: ["index", "middle", "ring"], label: "Three fingers moving a window" },
      scene: screen(win(20, 18, 110, 70, "Notes", "moving-window") + '<g class="moving-window">' + lines(28, 40, 4, 80) + "</g>", "Window follows the hand")
    },
    "window-swipe": {
      dur: 3.6,
      hand: { straight: { index: -6, middle: -1, ring: 4, pinky: 10 }, active: ["index", "middle", "ring", "pinky"], label: "Four fingers swiping up" },
      scene: screen('<g class="swipe-window">' + win(60, 40, 120, 72, "Browser") + "</g>", "Window maximizes")
    },
    horns: {
      dur: 3.6,
      hand: { straight: { index: -8, pinky: 12 }, curled: ["middle", "ring"], active: ["index", "pinky"], label: "Index and pinky held up",
        extra: '<g class="hold-ring-wrap">' + ring(176, 40, 20, "hold-ring") + "</g>" },
      scene: screen(win(24, 20, 120, 80, "Mail") + win(96, 50, 120, 80, "Editor", "alt-front") +
        '<g class="alttab"><rect x="40" y="52" width="160" height="56" rx="8" class="scr-menu"/>' +
        '<rect x="54" y="62" width="40" height="30" rx="4" class="scr-card c0 alttab-sel"/><rect x="100" y="62" width="40" height="30" rx="4" class="scr-card c1"/>' +
        '<rect x="146" y="62" width="40" height="30" rx="4" class="scr-card c2"/></g>', "Switch application")
    },
    "thumb-pinky": {
      dur: 6,
      hand: { straight: {}, curled: ["index", "middle", "ring"], bend: { pinky: 10 }, thumb: [38, 0.72, true], active: ["pinky", "thumb"], label: "Thumb and pinky held twice to close" },
      scene: screen(win(40, 24, 160, 96, "Old draft", "close-window") + '<g class="close-window">' + lines(52, 48, 5, 120) + "</g>" +
        '<g class="close-armed"><rect x="56" y="62" width="128" height="28" rx="6" class="scr-warn"/>' +
        '<text x="120" y="79.5" class="scr-text warn" text-anchor="middle">Repeat to confirm</text></g>', "Window closes after confirmation")
    },
    emergency: {
      dur: 4.5,
      hand: { straight: { index: -6, middle: -1, ring: 4, pinky: 10 }, thumb: [-42, 1, false], active: ["thumb", "index", "middle", "ring", "pinky"],
        label: "Open palm held for 1.5 seconds", extra: '<g class="em-ring">' + PALM + "</g>" },
      scene: screen(win(26, 18, 150, 90, "Any app") + '<g class="em-cursor" style="transform:translate(150px,80px)">' + CURSOR + "</g>" +
        '<g class="em-badge"><rect x="62" y="56" width="116" height="34" rx="17" class="scr-stop"/>' +
        '<text x="120" y="77.5" class="scr-text stop" text-anchor="middle">CONTROL STOPPED</text></g>', "All gesture control stops")
    }
  };

  function render(el) {
    var key = el.getAttribute("data-demo");
    var demo = DEMOS[key];
    if (!demo) return;
    el.classList.add("demo", "demo-" + key);
    el.style.setProperty("--dur", demo.dur + "s");
    el.innerHTML =
      '<div class="demo-stage">' +
      '<div class="demo-hand">' + buildHand(demo.hand) + "</div>" +
      '<div class="demo-arrow" aria-hidden="true">&rarr;</div>' +
      '<div class="demo-screen">' + demo.scene + "</div>" +
      "</div>" +
      '<div class="demo-controls">' +
      '<button type="button" class="demo-btn" data-act="pause" aria-label="Pause animation">Pause</button>' +
      '<button type="button" class="demo-btn" data-act="replay" aria-label="Replay animation">Replay</button>' +
      '<button type="button" class="demo-btn" data-act="slow" aria-pressed="false" aria-label="Slow motion">0.5&times;</button>' +
      "</div>";
  }

  function replay(el) {
    var stage = el.querySelector(".demo-stage");
    var clone = stage.cloneNode(true);
    stage.parentNode.replaceChild(clone, stage);
  }

  function wire(el) {
    el.addEventListener("click", function (ev) {
      var btn = ev.target.closest(".demo-btn");
      if (!btn) return;
      var act = btn.getAttribute("data-act");
      if (act === "pause") {
        var paused = el.classList.toggle("paused");
        btn.textContent = paused ? "Play" : "Pause";
      } else if (act === "replay") {
        replay(el);
        el.classList.remove("paused");
        el.querySelector('[data-act="pause"]').textContent = "Pause";
      } else if (act === "slow") {
        var slow = el.classList.toggle("slow");
        btn.setAttribute("aria-pressed", slow ? "true" : "false");
        replay(el);
      }
    });
  }

  function init(root) {
    var nodes = (root || document).querySelectorAll("[data-demo]");
    Array.prototype.forEach.call(nodes, function (el) {
      render(el);
      wire(el);
    });
    // Pause animations that are off screen to save CPU / battery.
    if ("IntersectionObserver" in window) {
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (e) { e.target.classList.toggle("offscreen", !e.isIntersecting); });
      }, { rootMargin: "100px" });
      Array.prototype.forEach.call(nodes, function (el) { io.observe(el); });
    }
  }

  window.GestureDemo = { init: init, render: render, demos: DEMOS, buildHand: buildHand };
})();
