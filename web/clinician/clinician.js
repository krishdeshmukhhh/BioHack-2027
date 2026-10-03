// Clinician portal entry: patient list, live pump card, profiles and propose form,
// prescription list, chart, alarm timeline and audit trail. All from data.js.

import { loadLanguage, ml, mlHr, renderFooter, simLabelHtml, t } from "/shared/core.js";
import { createPumpStore, pumpIdFromUrl } from "/shared/data.js";
import { initLanguageSelect, savedLang } from "/shared/lang.js";
import { initNightToggle } from "/shared/theme.js";
import { hasStatus, renderConnection, setHtml, setText } from "/shared/ui.js";
import { initAudit } from "./audit.js";
import { initChart } from "./chart.js";
import { initHistory } from "./history.js";
import { initPatients } from "./patients.js";
import { initProfiles } from "./profiles.js";
import { initPropose } from "./propose.js";
import { initSummary } from "./summary.js";
import { initTimeline } from "./timeline.js";

const $ = (id) => document.getElementById(id);
const pumpId = pumpIdFromUrl();

await loadLanguage(savedLang());
renderFooter($("footer"));
const repaintNight = initNightToggle($("night-toggle"));

const store = createPumpStore(pumpId).start();
let patientName = null;
let shownPatient;

function renderLive(state) {
  renderConnection($("conn"), $("conn-live"), state);
  $("pump-name").textContent = patientName
    ? `${patientName} · ${t("clin_pump", { pump: pumpId })}`
    : t("clin_pump", { pump: pumpId });
  const s = hasStatus(state) ? state.status : null;
  setText($("live-state"), s ? t(`state_${s.state}`) : t("waiting_for_pump"));
  setText($("live-rate"), s ? mlHr(s.rate_ml_hr) : "–");
  setText($("live-version"), s?.prescription_version
    ? t("version", { version: s.prescription_version }) : t("clin_none"));
  setText($("live-delivered"), s
    ? t("family_of_target", { delivered: ml(s.delivered_ml), target: ml(s.target_ml) }) : "–");
  setHtml($("sim-slot"), s?.simulated === false ? "" : simLabelHtml(), { fade: false });
}
store.subscribe(renderLive);

const chart = initChart(store);
const profiles = initProfiles();
const summary = initSummary();
const patients = initPatients(store, (rows) => {
  const me = rows.find((p) => p.pump_id === pumpId);
  patientName = me?.display_name || null;
  if (me) chart.setPatient(me.id);
  else chart.noPatients();
  if (me?.id !== shownPatient) {
    shownPatient = me?.id;
    profiles.setPatient(me?.id);
    summary.setPatient(me?.id);
  }
  renderLive(store.state);
});
initHistory(store);
const propose = initPropose(pumpId);
initTimeline(store);
const audit = initAudit(store);

initLanguageSelect($("language"), () => {
  renderFooter($("footer"));
  repaintNight();
  propose?.rerender?.();
  profiles.rerender();
  summary.rerender();
  audit.rerender();
  chart.rerender();
  patients.render();
  store.rerender();
});
