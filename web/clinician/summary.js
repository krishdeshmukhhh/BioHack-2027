// Portal: rule-based weekly summary (FR-21). The hub sends facts as codes and
// numbers (docs/API.md WeeklySummary); every word here comes from the strings file.

import { currentLang, escapeHtml, fmtNumber, simLabelHtml, t } from "/shared/core.js";
import { api, isNotAvailable } from "/shared/data.js";
import { setHtml } from "/shared/ui.js";

const $ = (id) => document.getElementById(id);

const fmtDay = (iso) =>
  new Date(`${iso}T00:00:00Z`).toLocaleDateString(currentLang(),
    { month: "short", day: "numeric", timeZone: "UTC" });

export function initSummary() {
  let summary = null;
  let message = "loading";

  function render() {
    const el = $("summary");
    if (!summary) {
      setHtml(el, `<p class="empty">${escapeHtml(t(message))}</p>`, { fade: false });
      return;
    }
    const s = summary;
    if (!s.days) {
      setHtml(el, `<p class="empty">${escapeHtml(t("summary_none"))}</p>`, { fade: false });
      return;
    }
    const alarms = Object.entries(s.alarms_by_code || {})
      .map(([code, n]) => `${t(`alarm_${code}`)}: ${n}`).join(", ");
    const lines = [
      s.delivered_pct != null && t("summary_delivered", { pct: fmtNumber(s.delivered_pct), days: s.days }),
      s.prior_week_delivered_pct != null && t("summary_prior", { pct: fmtNumber(s.prior_week_delivered_pct) }),
      s.trend && t(`trend_${s.trend}`),
      t("summary_under", { count: s.days_under_target }),
      s.alarm_count ? t("summary_alarms", { count: s.alarm_count, list: alarms }) : t("summary_no_alarms"),
    ].filter(Boolean);
    setHtml(el,
      `<p class="hint">${escapeHtml(t("summary_range", { from: fmtDay(s.from_date), to: fmtDay(s.to_date) }))}` +
      `${s.simulated ? ` ${simLabelHtml()}` : ""}</p>` +
      `<ul class="summary-list">${lines.map((l) => `<li>${escapeHtml(l)}</li>`).join("")}</ul>`,
      { fade: false });
  }

  render();
  return {
    async setPatient(patientId) {
      try {
        summary = patientId ? await api.summary(patientId) : null;
        message = patientId ? "summary_none" : "clin_unavailable";
      } catch (err) {
        summary = null;
        message = isNotAvailable(err) ? "clin_unavailable" : "error_generic";
      }
      render();
    },
    rerender: render,
  };
}
