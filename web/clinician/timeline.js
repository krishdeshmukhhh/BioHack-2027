// Portal: alarm timeline for the selected pump. Uses the hub's Alerts when it has
// them; otherwise pairs up alarm_raised / alarm_cleared pump events from SSE.

import { escapeHtml, fmtDateTime, icon, simLabelHtml, t } from "/shared/core.js";
import { setHtml } from "/shared/ui.js";

const $ = (id) => document.getElementById(id);

function fromEvents(events) {
  const out = [];
  const open = new Map();
  for (const e of [...events].reverse()) { // oldest first
    if (e.type === "alarm_raised") {
      const a = { alarm: e.alarm, active: true, raised_at: e.received_at, cleared_at: null, simulated: e.simulated };
      open.set(e.alarm, a);
      out.push(a);
    } else if (e.type === "alarm_cleared" && open.has(e.alarm)) {
      Object.assign(open.get(e.alarm), { active: false, cleared_at: e.received_at });
      open.delete(e.alarm);
    }
  }
  return out.reverse();
}

export function initTimeline(store) {
  function render(state) {
    const alerts = state.alerts.length ? [...state.alerts] : fromEvents(state.events);
    alerts.sort((a, b) => (b.raised_at || "").localeCompare(a.raised_at || ""));
    const html = alerts.length
      ? alerts.map((a) => {
        const minutes = a.cleared_at
          ? Math.max(1, Math.round((Date.parse(a.cleared_at) - Date.parse(a.raised_at)) / 60000))
          : 0;
        const status = a.active
          ? `<span class="chip tone-danger">${icon("alert")}<span>${escapeHtml(t("timeline_active"))}</span></span>`
          : `<span class="chip tone-ok">${icon("check")}<span>${escapeHtml(
            t("timeline_cleared", { time: fmtDateTime(a.cleared_at), minutes }))}</span></span>`;
        return `<li><time datetime="${escapeHtml(a.raised_at)}">${escapeHtml(fmtDateTime(a.raised_at))}</time>` +
          `<strong>${escapeHtml(t(`alarm_${a.alarm}`))}</strong>${status}${a.simulated ? simLabelHtml() : ""}</li>`;
      }).join("")
      : `<li class="empty">${escapeHtml(t("timeline_empty"))}</li>`;
    setHtml($("timeline"), html, { fade: false });
  }
  store.subscribe(render);
}
