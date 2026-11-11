// Sets the theme (light or dark) before the page is drawn (no flash).
// Loaded in <head> without "defer". Without a stored choice, the system setting decides.
(function () {
  "use strict";
  let theme = null;
  try {
    theme = window.localStorage.getItem("mtas-theme");
  } catch (error) {
    // no storage (private window)
  }
  if (theme !== "light" && theme !== "dark") {
    const dark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    theme = dark ? "dark" : "light";
  }
  document.documentElement.dataset.theme = theme;
})();
