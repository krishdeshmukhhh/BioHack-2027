// Language choice (FR-25). Each language is one strings.<lang>.js file.

import { applyStrings, currentLang, loadLanguage } from "./core.js";

export const LANGUAGES = [
  { code: "en", name: "English" },
  { code: "es", name: "Español" },
];
const KEY = "sp-lang";

export function savedLang() {
  try {
    const code = localStorage.getItem(KEY);
    if (LANGUAGES.some((l) => l.code === code)) return code;
  } catch {
    /* storage blocked */
  }
  const browser = (navigator.language || "en").slice(0, 2);
  return LANGUAGES.some((l) => l.code === browser) ? browser : "en";
}

/** Fill a <select> with the languages; on change load strings and call onChange. */
export function initLanguageSelect(select, onChange) {
  select.innerHTML = LANGUAGES.map(
    (l) => `<option value="${l.code}" lang="${l.code}">${l.name}</option>`,
  ).join("");
  select.value = currentLang();
  select.addEventListener("change", async () => {
    await loadLanguage(select.value);
    try {
      localStorage.setItem(KEY, select.value);
    } catch {
      /* storage blocked: lasts for this page only */
    }
    applyStrings();
    onChange?.();
  });
}
