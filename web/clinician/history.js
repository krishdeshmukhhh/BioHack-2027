// Portal: prescription list with the status chip (FR-7). The chip shows exactly
// the state the hub reports: it reads only the store, which SSE keeps current.

import { chipHtml, chipInfo, escapeHtml, fmtTime, ml, mlHr, t, userName } from "/shared/core.js";
import { prescriptionList } from "/shared/data.js";
import { setHtml } from "/shared/ui.js";

const $ = (id) => document.getElementById(id);

function itemHtml(rx, availability) {
  const c = chipInfo(rx, availability);
  const summary = t("clin_summary", {
    mode: t(`mode_${rx.mode}`), rate: mlHr(rx.rate_ml_hr), volume: ml(rx.volume_ml),
  });
  const times = [
    rx.proposed_at && t("clin_time_proposed", { time: fmtTime(rx.proposed_at) }),
    rx.confirmed_by && t("clin_confirmed_by", { who: userName(rx.confirmed_by) }),
    rx.sent_at && t("clin_time_sent", { time: fmtTime(rx.sent_at) }),
    rx.resolved_at && rx.state !== "superseded" && rx.reject_reason !== "declined" &&
      t("clin_time_resolved", { time: fmtTime(rx.resolved_at) }),
  ].filter(Boolean);
  return (
    `<li class="rx rx-${escapeHtml(rx.state)}">` +
    `<div class="rx-head"><h3>${escapeHtml(t("clin_values_heading", { version: rx.version }))}</h3>` +
    `${chipHtml(rx, availability)}</div>` +
    `<p class="rx-summary">${escapeHtml(summary)}</p>` +
    (c.detail ? `<p class="rx-detail">${escapeHtml(c.detail)}</p>` : "") +
    (rx.note ? `<p class="rx-note">${escapeHtml(rx.note)}</p>` : "") +
    `<p class="rx-times">${times.map(escapeHtml).join(" · ")}</p>` +
    "</li>"
  );
}

export function initHistory(store) {
  const seen = new Map(); // version -> last announced label

  store.subscribe((state) => {
    const list = prescriptionList(state);
    setHtml($("history"), list.length
      ? list.map((rx) => itemHtml(rx, state.availability)).join("")
      : `<li class="empty">${escapeHtml(t("clin_history_empty"))}</li>`, { fade: false });

    // Speak chip changes after the first render (not the whole list on load).
    // When several change at once, speak the newest (list is newest first).
    const firstRender = seen.size === 0;
    let spoken = false;
    for (const rx of list) {
      const label = chipInfo(rx, state.availability).label;
      if (!firstRender && !spoken && seen.get(rx.version) !== label) {
        $("chip-live").textContent = t("clin_chip_announce", { version: rx.version, label });
        spoken = true;
      }
      seen.set(rx.version, label);
    }
  });
}
