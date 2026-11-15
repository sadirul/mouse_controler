/* Documentation site behaviour: theme toggle, navigation, copy buttons, lightbox. */
(function () {
  "use strict";

  function store(key, value) {
    try {
      if (value === undefined) return window.localStorage.getItem(key);
      window.localStorage.setItem(key, value);
    } catch (e) { /* storage unavailable (private mode, file:// restrictions) */ }
    return null;
  }

  /* ---- theme ---------------------------------------------------------------------- */
  var root = document.documentElement;
  var saved = store("hgm-theme");
  if (saved === "light" || saved === "dark") root.setAttribute("data-theme", saved);
  var themeBtn = document.getElementById("theme-toggle");
  function currentTheme() {
    var t = root.getAttribute("data-theme");
    if (t) return t;
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  }
  function syncThemeLabel() {
    if (themeBtn) themeBtn.textContent = currentTheme() === "dark" ? "☀ Light" : "☾ Dark";
  }
  if (themeBtn) {
    themeBtn.addEventListener("click", function () {
      var next = currentTheme() === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      store("hgm-theme", next);
      syncThemeLabel();
    });
  }
  syncThemeLabel();

  /* ---- mobile menu ---------------------------------------------------------------- */
  var sidebar = document.getElementById("sidebar");
  var menuBtn = document.getElementById("menu-toggle");
  if (menuBtn && sidebar) {
    menuBtn.addEventListener("click", function () {
      var open = sidebar.classList.toggle("open");
      menuBtn.setAttribute("aria-expanded", open ? "true" : "false");
    });
    sidebar.addEventListener("click", function (e) {
      if (e.target.closest("a")) {
        sidebar.classList.remove("open");
        menuBtn.setAttribute("aria-expanded", "false");
      }
    });
  }

  /* ---- active section highlighting ------------------------------------------------ */
  var links = Array.prototype.slice.call(document.querySelectorAll(".sidebar a[href^='#']"));
  var targets = links.map(function (a) { return document.getElementById(a.getAttribute("href").slice(1)); }).filter(Boolean);
  if ("IntersectionObserver" in window && targets.length) {
    var visible = {};
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) { visible[e.target.id] = e.isIntersecting; });
      var first = targets.filter(function (t) { return visible[t.id]; })[0];
      if (!first) return;
      links.forEach(function (a) { a.classList.toggle("active", a.getAttribute("href") === "#" + first.id); });
    }, { rootMargin: "-70px 0px -55% 0px" });
    targets.forEach(function (t) { io.observe(t); });
  }

  /* ---- copy to clipboard ------------------------------------------------------------ */
  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text);
    return new Promise(function (resolve, reject) {
      var ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand("copy") ? resolve() : reject(new Error("copy failed")); }
      catch (err) { reject(err); }
      finally { document.body.removeChild(ta); }
    });
  }
  Array.prototype.forEach.call(document.querySelectorAll(".code"), function (block) {
    var pre = block.querySelector("pre");
    if (!pre) return;
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "copy-btn";
    btn.textContent = "Copy";
    btn.setAttribute("aria-label", "Copy command to clipboard");
    btn.addEventListener("click", function () {
      copyText(pre.innerText.replace(/\n$/, "")).then(function () {
        btn.textContent = "Copied ✓";
        btn.classList.add("done");
      }, function () {
        btn.textContent = "Press Ctrl+C";
        var range = document.createRange();
        range.selectNodeContents(pre);
        var sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(range);
      });
      setTimeout(function () { btn.textContent = "Copy"; btn.classList.remove("done"); }, 1800);
    });
    block.appendChild(btn);
  });

  /* ---- screenshot lightbox ---------------------------------------------------------- */
  var lightbox = document.getElementById("lightbox");
  if (lightbox) {
    var big = lightbox.querySelector("img");
    document.addEventListener("click", function (e) {
      var img = e.target.closest(".gallery img");
      if (img) {
        big.src = img.src;
        big.alt = img.alt;
        lightbox.classList.add("open");
      } else if (e.target.closest("#lightbox")) {
        lightbox.classList.remove("open");
      }
    });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") lightbox.classList.remove("open"); });
  }

  /* ---- back to top ------------------------------------------------------------------ */
  var toTop = document.getElementById("to-top");
  if (toTop) {
    window.addEventListener("scroll", function () { toTop.classList.toggle("show", window.scrollY > 900); }, { passive: true });
  }

  /* ---- gesture demos ----------------------------------------------------------------- */
  if (window.GestureDemo) {
    window.GestureDemo.init(document);
    var hero = document.getElementById("hero-demo");
    if (hero) {
      var d = window.GestureDemo.demos.move;
      hero.innerHTML = '<div>' + window.GestureDemo.buildHand(d.hand) + '</div><div>' + d.scene + '</div>';
    }
    if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      Array.prototype.forEach.call(document.querySelectorAll(".demo"), function (el) {
        el.classList.add("paused");
        var b = el.querySelector('[data-act="pause"]');
        if (b) b.textContent = "Play";
      });
    }
  }

  var year = document.getElementById("year");
  if (year) year.textContent = String(new Date().getFullYear());
})();
