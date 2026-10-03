// Family app: alert screen (FR-14, NFR-A4, NFR-A6).
// Picture, cause, numbered steps, and "Done". "Done" only acknowledges on this
// phone; the alarm is cleared at the pump (FR-16), and the screen follows the hub.

import { escapeHtml, fmtTime, icon, t, tList } from "/shared/core.js";
import { currentAlarm } from "/shared/data.js";
import { beep, isUnlocked, speak, unlock, vibrate } from "/shared/speech.js";
import { setHtml } from "/shared/ui.js";
import { alertPicture } from "./pictures.js";
import { onSettingsChange, prefsFor } from "./settings.js";

const $ = (id) => document.getElementById(id);
const REPEAT_MS = 30000;

export function initAlerts(store) {
  let shownKey = null; // which alarm is on screen
  let acknowledged = false;
  let firstSeenAt = null;
  let repeatTimer = null;
  let clearedTimer = null;

  // "Turn on alerts": one tap unlocks vibration, sound and speech (NFR-A6, R7).
  $("enable-btn").addEventListener("click", () => {
    unlock();
    $("enable-alerts").hidden = true;
    $("enabled-note").hidden = false;
    $("enabled-note").textContent = t("alerts_enabled");
    if (shownKey && !acknowledged) cue(store.state);
  });

  $("alert-done").addEventListener("click", () => {
    acknowledged = true;
    stopRepeat();
    render(store.state);
    $("alert-waiting").focus();
  });

  function cue(state) {
    const now = currentAlarm(state);
    if (!now || !isUnlocked()) return;
    const prefs = prefsFor();
    if (prefs.vibrate) vibrate();
    if (prefs.sound) beep();
    if (prefs.speak) {
      speak(t("alert_spoken", { alarm: t(`alarm_${now.alarm}`), cause: t(`cause_${now.alarm}`) }));
    }
  }

  function stopRepeat() {
    clearInterval(repeatTimer);
    repeatTimer = null;
  }

  function render(state) {
    const now = currentAlarm(state);
    const card = $("alert");
    const key = now ? `${now.alarm}|${now.since || ""}` : null;

    if (key !== shownKey) {
      if (now) {
        // A new alarm: reset, cue every available path, repeat until "Done".
        acknowledged = false;
        firstSeenAt = now.since || new Date().toISOString();
        clearTimeout(clearedTimer);
        $("alert-cleared").hidden = true;
        cue(state);
        stopRepeat();
        repeatTimer = setInterval(() => !acknowledged && cue(store.state), REPEAT_MS);
      } else if (shownKey) {
        // The hub reports the alarm cleared.
        stopRepeat();
        $("alert-cleared").hidden = false;
        setHtml($("alert-cleared"), `${icon("check")}<span>${escapeHtml(t("alert_cleared"))}</span>`);
        if (isUnlocked() && prefsFor().speak) speak(t("alert_cleared"));
        clearedTimer = setTimeout(() => ($("alert-cleared").hidden = true), 10000);
      }
      shownKey = key;
    }

    card.hidden = !now;
    if (!now) return;

    const alarmName = t(`alarm_${now.alarm}`);
    setHtml($("alert-head"),
      `${icon("alert")}<span>${escapeHtml(alarmName)}</span>`, { fade: false });
    $("alert-started").textContent = t("alert_started", { time: fmtTime(firstSeenAt) });
    setHtml($("alert-pic"), alertPicture(now.alarm), { fade: false });
    $("alert-cause").textContent = t(`cause_${now.alarm}`);
    setHtml($("alert-steps"),
      tList(`steps_${now.alarm}`).map((s) => `<li>${escapeHtml(s)}</li>`).join(""), { fade: false });

    $("alert-done").hidden = acknowledged;
    $("alert-waiting").hidden = !acknowledged;
    if (acknowledged) {
      setHtml($("alert-waiting"), `${icon("clock")}<span>${escapeHtml(t("alert_waiting"))}</span>`);
    }
  }

  onSettingsChange(() => render(store.state)); // new language: same alarm, new copy
  store.subscribe(render);
}
