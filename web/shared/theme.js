// Night mode switch (FR-26). The saved choice is applied by a tiny inline script in
// each page's <head> so there is no flash of the day palette.

import { escapeHtml, icon, t } from "./core.js";

const KEY = "sp-theme";

function save(theme) {
  try {
    localStorage.setItem(KEY, theme);
  } catch {
    /* storage blocked: the choice lasts for this page only */
  }
}

export function initNightToggle(button) {
  const root = document.documentElement;
  const paint = () => {
    const night = root.dataset.theme === "night";
    button.setAttribute("aria-pressed", String(night));
    button.innerHTML = `${icon("moon")}<span>${escapeHtml(t("night_mode"))}</span>`;
  };
  button.addEventListener("click", () => {
    const night = root.dataset.theme !== "night";
    if (night) root.dataset.theme = "night";
    else delete root.dataset.theme;
    save(night ? "night" : "day");
    paint();
  });
  paint();
}
