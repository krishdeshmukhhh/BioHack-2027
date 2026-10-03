// Family app: live page (PLAN phase 1). Renders only from the shared store in
// web/shared/data.js. Change review and alerts are added in later groups.

import {
  applyStrings, escapeHtml, fmtTime, icon, ml, mlHr, renderFooter, simLabelHtml, t,
} from "/shared/core.js";
import { createPumpStore, pumpIdFromUrl } from "/shared/data.js";
import { initNightToggle } from "/shared/theme.js";

const $ = (id) => document.getElementById(id);

const STATE_ICON = {
  idle: "info", priming: "clock", running: "play", paused: "pause",
  alarm: "alert", complete: "check",
};
const STATE_TONE = {
  idle: "neutral", priming: "info", running: "ok", paused: "warn",
  alarm: "danger", complete: "ok",
};

/** Set innerHTML only when it changes, so aria-live does not re-announce every tick. */
function setHtml(el, html) {
  if (el.dataset.html === html) return false;
  el.dataset.html = html;
  el.innerHTML = html;
  el.classList.remove("fade");
  void el.offsetWidth; // restart the short fade
  el.classList.add("fade");
  return true;
}

function setText(el, text) {
  if (el.textContent !== text) el.textContent = text;
}

function renderConnection(state) {
  const el = $("conn");
  const time = fmtTime(state.lastUpdateAt);
  let tone, ic, title, body = "";
  if (state.stream === "connecting") {
    tone = "neutral"; ic = "clock"; title = t("connecting");
  } else if (state.stream === "lost") {
    // The stream to the hub dropped. EventSource keeps retrying in the background.
    tone = "warn"; ic = "wifiOff";
    title = time ? t("offline_last_update", { time }) : t("offline_no_update");
    body = t("hub_lost");
  } else if (!state.availability.online) {
    tone = "warn"; ic = "wifiOff";
    const since = fmtTime(state.availability.last_seen_at);
    title = since ? t("pump_offline_since", { time: since }) : t("pump_offline");
    body = t("pump_offline_body");
  } else {
    tone = "ok"; ic = "wifi"; title = t("online_last_update", { time });
  }
  const kind = state.stream === "open" ? (state.availability.online ? "online" : "offline")
    : state.stream;
  const live = $("conn-live");
  if (live.dataset.kind !== kind) {
    live.dataset.kind = kind;
    // Stay quiet on first load while connecting; speak every later change.
    if (kind !== "connecting") live.textContent = body ? `${title}. ${body}` : title;
  }
  el.className = `banner conn tone-${tone}`;
  setHtml(el, `${icon(ic)}<span><strong>${escapeHtml(title)}</strong>` +
    (body ? `<span class="conn-body">${escapeHtml(body)}</span>` : "") + "</span>");
}

function renderStatus(state) {
  const s = state.status;
  const pumpState = s?.state || "idle";
  const tone = STATE_TONE[pumpState] || "neutral";

  $("state").className = `state tone-text-${tone}`;
  setHtml($("state"), s
    ? `${icon(STATE_ICON[pumpState] || "info")}<span>${escapeHtml(t(`state_${pumpState}`))}</span>`
    : `<span>${escapeHtml(t("loading"))}</span>`);

  const alarmLine = $("alarm-line");
  if (s?.alarm) {
    alarmLine.hidden = false;
    setHtml(alarmLine, `${icon("alert")}<span>${escapeHtml(
      t("alarm_line", { alarm: t(`alarm_${s.alarm}`) }))}</span>`);
  } else {
    alarmLine.hidden = true;
  }

  const delivered = s?.delivered_ml || 0;
  const target = s?.target_ml || 0;
  const pct = target > 0 ? Math.min(100, Math.round((delivered / target) * 100)) : 0;
  const text = target > 0
    ? t("family_of_target", { delivered: ml(delivered), target: ml(target) })
    : t("family_no_feed");
  setText($("delivered-text"), text);
  const meter = $("meter");
  meter.setAttribute("aria-valuenow", String(pct));
  meter.setAttribute("aria-valuetext", text);
  $("meter-fill").style.width = `${pct}%`;

  setText($("rate"), s ? mlHr(s.rate_ml_hr) : "–");
  setText($("version"), s?.prescription_version
    ? t("version", { version: s.prescription_version })
    : t("clin_none"));
  setText($("updated"), state.lastUpdateAt
    ? t("updated_at", { time: fmtTime(state.lastUpdateAt) })
    : t("never_updated"));

  // S8: label simulated data. Shown until a real, non-simulated status says otherwise.
  setHtml($("sim-slot"), s?.simulated === false ? "" : simLabelHtml());
}

function render(state) {
  renderConnection(state);
  renderStatus(state);
}

applyStrings();
renderFooter($("footer"));
initNightToggle($("night-toggle"));
createPumpStore(pumpIdFromUrl()).start().subscribe(render);
