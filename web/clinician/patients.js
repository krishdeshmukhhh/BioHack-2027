// Portal: patient list, exceptions first (FR-19). Exception codes come from the
// hub (docs/API.md), including `alarm_active` for a live alarm (FR-15). The list
// is refreshed every few seconds instead of opening a live stream per patient:
// browsers allow only 6 connections per host, and each SSE stream holds one.
// The selected pump's own stream (already open) names its alarm without delay.

import { escapeHtml, icon, simLabelHtml, t } from "/shared/core.js";
import { api, currentAlarm, isNotAvailable } from "/shared/data.js";
import { setHtml, setText } from "/shared/ui.js";

const $ = (id) => document.getElementById(id);
const REFRESH_MS = 5000;

const EXC_ICON = {
  offline: "wifiOff", under_target: "drop", night_alarms: "clock", alarm: "alert", alarm_active: "alert",
};

/**
 * @param currentStore the selected pump's store
 * @param onPatients   called with the patient rows whenever they load
 */
export function initPatients(currentStore, onPatients) {
  const currentPump = currentStore.state.pumpId;
  let patients = [];
  let unavailable = false;
  let failed = false;
  let loaded = false;

  // For the selected pump, the live stream is newer than the last list refresh:
  // show its alarm by name, or drop a stale `alarm_active` once it has cleared.
  function exceptionsOf(p) {
    if (p.pump_id !== currentPump || !currentStore.state.status) return [...p.exceptions];
    const list = p.exceptions.filter((e) => e !== "alarm_active");
    const alarm = currentAlarm(currentStore.state)?.alarm;
    if (alarm) list.unshift(`alarm:${alarm}`);
    return list;
  }

  function chip(code) {
    const [kind, alarm] = code.split(":");
    const label = kind === "alarm"
      ? t("exc_alarm", { alarm: t(`alarm_${alarm}`) })
      : t(`exc_${kind}`);
    const tone = kind.startsWith("alarm") ? "danger" : "warn";
    return `<span class="chip tone-${tone}">${icon(EXC_ICON[kind] || "alert")}<span>${escapeHtml(label)}</span></span>`;
  }

  function render() {
    $("patients-error").hidden = !failed;
    setText($("patients-error"), t(loaded ? "patients_stale" : "error_network"));
    if (unavailable) {
      setText($("patients-count"), "");
      setHtml($("patients"), `<li class="empty">${escapeHtml(t("clin_unavailable"))}</li>`, { fade: false });
      return;
    }
    // A live alarm first, then other exceptions, then the rest (stable otherwise).
    const rank = (exc) => (exc.some((e) => e.startsWith("alarm")) ? 2 : exc.length ? 1 : 0);
    const rows = patients
      .map((p, i) => ({ p, i, exc: exceptionsOf(p) }))
      .sort((a, b) => rank(b.exc) - rank(a.exc) || a.i - b.i);
    const html = rows.map(({ p, exc }) => {
      const current = p.pump_id === currentPump;
      const chips = exc.length
        ? exc.map(chip).join("")
        : `<span class="chip tone-ok">${icon("check")}<span>${escapeHtml(t("exc_none"))}</span></span>`;
      const action = current
        ? `<span class="current" aria-current="page">${escapeHtml(t("clin_current_patient"))}</span>`
        : `<a class="btn btn-small" data-pump="${escapeHtml(p.pump_id)}" href="?pump=${encodeURIComponent(p.pump_id)}">` +
          `${escapeHtml(t("clin_open_patient"))}<span class="visually-hidden"> ${escapeHtml(p.display_name)}</span></a>`;
      return `<li class="patient${current ? " is-current" : ""}">` +
        `<div class="patient-main"><strong>${escapeHtml(p.display_name)}</strong>` +
        `<span class="muted">${escapeHtml(t("clin_pump", { pump: p.pump_id }))}</span>` +
        (p.simulated ? simLabelHtml() : "") + `</div>` +
        `<div class="patient-chips">${chips}</div>${action}</li>`;
    }).join("");
    const focusedPump = $("patients").contains(document.activeElement)
      ? document.activeElement.dataset.pump : null;
    const changed = setHtml($("patients"), html || `<li class="empty">${escapeHtml(t(loaded ? "patients_empty" : "loading"))}</li>`, { fade: false });
    if (changed && focusedPump) {
      const link = [...$("patients").querySelectorAll("[data-pump]")]
        .find((el) => el.dataset.pump === focusedPump);
      link?.focus({ preventScroll: true });
    }
    setText($("patients-count"), loaded ? t("patients_count", {
      count: rows.length, attention: rows.filter((r) => r.exc.length).length,
    }) : "");
  }

  async function load() {
    try {
      patients = await api.patients();
      unavailable = false;
      failed = false;
      loaded = true;
      onPatients?.(patients);
    } catch (err) {
      unavailable = isNotAvailable(err);
      failed = !unavailable;
      if (unavailable) onPatients?.([]); // dependent sections show "not available"
      else console.warn("patients", err);
    }
    render();
  }

  currentStore.subscribe(render);
  load();
  setInterval(load, REFRESH_MS);
  return { render };
}
