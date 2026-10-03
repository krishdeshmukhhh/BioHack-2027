// Clinician portal entry: live pump card, propose form, prescription list.
// Patient list, charts, alarm timeline and audit arrive in the next group.

import { applyStrings, ml, mlHr, renderFooter, simLabelHtml, t } from "/shared/core.js";
import { createPumpStore, pumpIdFromUrl } from "/shared/data.js";
import { initNightToggle } from "/shared/theme.js";
import { hasStatus, renderConnection, setHtml, setText } from "/shared/ui.js";
import { initHistory } from "./history.js";
import { initPropose } from "./propose.js";

const $ = (id) => document.getElementById(id);
const pumpId = pumpIdFromUrl();

applyStrings();
renderFooter($("footer"));
initNightToggle($("night-toggle"));
$("pump-name").textContent = t("clin_pump", { pump: pumpId });

const store = createPumpStore(pumpId).start();
store.subscribe((state) => {
  renderConnection($("conn"), $("conn-live"), state);
  const s = hasStatus(state) ? state.status : null;
  setText($("live-state"), s ? t(`state_${s.state}`) : t("waiting_for_pump"));
  setText($("live-rate"), s ? mlHr(s.rate_ml_hr) : "–");
  setText($("live-version"), s?.prescription_version
    ? t("version", { version: s.prescription_version }) : t("clin_none"));
  setText($("live-delivered"), s
    ? t("family_of_target", { delivered: ml(s.delivered_ml), target: ml(s.target_ml) }) : "–");
  setHtml($("sim-slot"), s?.simulated === false ? "" : simLabelHtml(), { fade: false });
});
initHistory(store);
initPropose(pumpId);
