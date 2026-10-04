// Family settings: language, who is using this phone, and that caregiver's alert
// preferences (FR-25, FR-29). Preferences live in this browser only.

import { t, userName } from "/shared/core.js";
import { initLanguageSelect } from "/shared/lang.js";
import { saveCaregiver, savedCaregiver } from "/shared/ui.js";

const $ = (id) => document.getElementById(id);
const PREFS = ["vibrate", "sound", "speak"];
const listeners = new Set();
const sessionPrefs = new Map();

export function caregiver() {
  return savedCaregiver();
}

export function prefsFor(id = caregiver()) {
  if (sessionPrefs.has(id)) return { ...sessionPrefs.get(id) };
  const prefs = { vibrate: true, sound: true, speak: true };
  try {
    Object.assign(prefs, JSON.parse(localStorage.getItem(`sp-prefs-${id}`) || "{}"));
  } catch {
    /* storage blocked or bad JSON: defaults */
  }
  return prefs;
}

function savePrefs(id, prefs) {
  sessionPrefs.set(id, { ...prefs });
  try {
    localStorage.setItem(`sp-prefs-${id}`, JSON.stringify(prefs));
  } catch {
    /* storage blocked */
  }
}

/** Called when the caregiver or language changes, so screens can re-render. */
export function onSettingsChange(fn) {
  listeners.add(fn);
}

function paintPrefs() {
  const id = caregiver();
  const prefs = prefsFor(id);
  $("prefs-legend").textContent = t("prefs_title", { who: userName(id) });
  for (const key of PREFS) $(`pref-${key}`).checked = !!prefs[key];
}

export function initSettings() {
  const select = $("caregiver");
  select.value = caregiver();
  select.addEventListener("change", () => {
    saveCaregiver(select.value);
    paintPrefs();
    listeners.forEach((fn) => fn());
  });
  for (const key of PREFS) {
    $(`pref-${key}`).addEventListener("change", (ev) => {
      const id = caregiver();
      savePrefs(id, { ...prefsFor(id), [key]: ev.target.checked });
    });
  }
  initLanguageSelect($("language"), () => {
    paintPrefs();
    listeners.forEach((fn) => fn());
  });
  paintPrefs();
}
