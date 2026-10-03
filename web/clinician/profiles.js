// Portal: feed profiles that pre-fill the propose form (FR-28).
// DEMO VALUES ONLY, not clinical guidance. They only fill the form: the
// clinician still proposes, the caregiver confirms, and the pump checks its limits.

import { escapeHtml, t } from "/shared/core.js";

const $ = (id) => document.getElementById(id);

const PROFILES = [
  { key: "profile_overnight", mode: "continuous", rate_ml_hr: 60, volume_ml: 500 },
  { key: "profile_day_bolus", mode: "bolus", rate_ml_hr: 120, volume_ml: 200 },
  { key: "profile_school", mode: "continuous", rate_ml_hr: 80, volume_ml: 300 },
];

export function initProfiles() {
  const paint = () => {
    $("profile-buttons").innerHTML = PROFILES.map((p, i) =>
      `<button type="button" class="btn btn-small" data-profile="${i}">${escapeHtml(t(p.key))}</button>`).join("");
  };
  $("profile-buttons").addEventListener("click", (ev) => {
    const button = ev.target.closest("[data-profile]");
    if (!button) return;
    const p = PROFILES[Number(button.dataset.profile)];
    const form = $("propose-form");
    form.elements.mode.value = p.mode;
    $("rate").value = String(p.rate_ml_hr);
    $("volume").value = String(p.volume_ml);
    $("profile-status").textContent = t("profile_applied", { name: t(p.key) });
    $("rate").focus();
  });
  paint();
  return { rerender: paint };
}
