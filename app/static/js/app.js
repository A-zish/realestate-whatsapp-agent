/* Shell behaviour: theme persistence + mobile sidebar. Deliberately tiny —
   no framework needed for this much interactivity. */

(function () {
  const KEY = "theme";

  window.toggleTheme = function () {
    const root = document.documentElement;
    const next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    try { localStorage.setItem(KEY, next); } catch (e) { /* private mode */ }
    document.querySelectorAll("[data-theme-icon]").forEach(function (el) {
      el.textContent = next === "dark" ? "☀️" : "🌙";
    });
  };

  window.toggleSidebar = function () {
    document.querySelector(".sidebar")?.classList.toggle("open");
    const existing = document.querySelector(".scrim");
    if (existing) { existing.remove(); return; }
    const scrim = document.createElement("div");
    scrim.className = "scrim";
    scrim.onclick = window.toggleSidebar;
    document.body.appendChild(scrim);
  };

  window.copyText = function (text, btn) {
    navigator.clipboard.writeText(text).then(function () {
      const original = btn.textContent;
      btn.textContent = "Copied";
      setTimeout(function () { btn.textContent = original; }, 1400);
    });
  };

  // Reflect the stored theme in the toggle icon on load (the theme attribute
  // itself is set by an inline script in <head> to avoid a flash).
  document.addEventListener("DOMContentLoaded", function () {
    const current = document.documentElement.getAttribute("data-theme");
    document.querySelectorAll("[data-theme-icon]").forEach(function (el) {
      el.textContent = current === "dark" ? "☀️" : "🌙";
    });
  });
})();
