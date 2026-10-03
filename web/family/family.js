// Family app entry: live page (PLAN phase 1) plus change review (phase 2).
// Renders only from the shared store in web/shared/data.js.

import {
  applyStrings, escapeHtml, fmtTime, icon, ml, mlHr, renderFooter, simLabelHtml, t,
} from "/shared/core.js";
import { createPumpStore, pumpIdFromUrl } from "/shared/data.js";
import { initNightToggle } from "/shared/theme.js";
import { hasStatus, renderConnection, setHtml, setText } from "/shared/ui.js";
import { initReview } from "./review.js";

const $ = (id) => document.getElementById(id);

const STATE_ICON = {
  idle: "info", priming: "clock", running: "play", paused: "pause",
  alarm: "alert", complete: "check",
};
const STATE_TONE = {
  idle: "neutral", priming: "info", running: "ok", paused: "warn",
  alarm: "danger", complete: "ok",
};

function renderStatus(state) {
  const s = hasStatus(state) ? state.status : null;
  const pumpState = s?.state;
  const tone = STATE_TONE[pumpState] || "neutral";

  $("state").className = `state tone-text-${tone}`;
  setHtml($("state"), s
    ? `${icon(STATE_ICON[pumpState] || "info")}<span>${escapeHtml(t(`state_${pumpState}`))}</span>`
    : `${icon("clock")}<span>${escapeHtml(t("waiting_for_pump"))}</span>`);

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
  setHtml($("sim-slot"), s?.simulated === false ? "" : simLabelHtml(), { fade: false });
}

applyStrings();
renderFooter($("footer"));
initNightToggle($("night-toggle"));

const store = createPumpStore(pumpIdFromUrl()).start();
store.subscribe((state) => {
  renderConnection($("conn"), $("conn-live"), state);
  renderStatus(state);
});
initReview(store);
