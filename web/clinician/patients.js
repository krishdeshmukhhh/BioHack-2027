// Portal: patient list, exceptions first (FR-19). Exception codes come from the
// hub (docs/API.md). A live alarm on a patient's pump also flags them (FR-15);
// that flag comes from the pump's own SSE stream, so it clears when the hub says so.

import { escapeHtml, icon, t } from "/shared/core.js";
import { api, createPumpStore, currentAlarm, isNotAvailable } from "/shared/data.js";
import { setHtml } from "/shared/ui.js";

const $ = (id) => document.getElementById(id);
const REFRESH_MS = 30000;

const EXC_ICON = { offline: "wifiOff", under_target: "drop", night_alarms: "clock", alarm: "alert" };

function liveAlarm(store) {
  return store ? currentAlarm(store.state)?.alarm || null : null;
}

/**
 * @param currentStore the selected pump's store (reused, not opened twice)
 * @param onPatients   called with the patient rows whenever they load
 */
export function initPatients(currentStore, onPatients) {
  const currentPump = currentStore.state.pumpId;
  const stores = new Map([[currentPump, currentStore]]);
  let patients = [];
  let unavailable = false;

  function storeFor(pumpId) {
    if (!stores.has(pumpId)) {
      const store = createPumpStore(pumpId).start();
      store.subscribe(render);
      stores.set(pumpId, store);
    }
    return stores.get(pumpId);
  }

  function exceptionsOf(p) {
    const list = [...p.exceptions];
    const alarm = liveAlarm(stores.get(p.pump_id));
    if (alarm) list.unshift(`alarm:${alarm}`);
    return list;
  }

  function chip(code) {
    const [kind, alarm] = code.split(":");
    const label = kind === "alarm"
      ? t("exc_alarm", { alarm: t(`alarm_${alarm}`) })
      : t(`exc_${kind}`);
    const tone = kind === "alarm" ? "danger" : "warn";
    return `<span class="chip tone-${tone}">${icon(EXC_ICON[kind] || "alert")}<span>${escapeHtml(label)}</span></span>`;
  }

  function render() {
    if (unavailable) {
      setHtml($("patients"), `<li class="empty">${escapeHtml(t("clin_unavailable"))}</li>`, { fade: false });
      return;
    }
    // A live alarm first, then other exceptions, then the rest (stable otherwise).
    const rank = (exc) => (exc.some((e) => e.startsWith("alarm:")) ? 2 : exc.length ? 1 : 0);
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
        : `<a class="btn btn-small" href="?pump=${encodeURIComponent(p.pump_id)}">` +
          `${escapeHtml(t("clin_open_patient"))}<span class="visually-hidden"> ${escapeHtml(p.display_name)}</span></a>`;
      return `<li class="patient${current ? " is-current" : ""}">` +
        `<div class="patient-main"><strong>${escapeHtml(p.display_name)}</strong>` +
        `<span class="muted">${escapeHtml(t("clin_pump", { pump: p.pump_id }))}</span></div>` +
        `<div class="patient-chips">${chips}</div>${action}</li>`;
    }).join("");
    setHtml($("patients"), html, { fade: false });
  }

  async function load() {
    try {
      patients = await api.patients();
      unavailable = false;
      for (const p of patients) storeFor(p.pump_id);
      onPatients?.(patients);
    } catch (err) {
      unavailable = isNotAvailable(err);
      if (!unavailable) console.warn("patients", err);
    }
    render();
  }

  currentStore.subscribe(render);
  load();
  setInterval(load, REFRESH_MS);
  return { render };
}
