// Portal: feed profiles that pre-fill the propose form (FR-28), from
// /api/patients/{id}/profiles. DEMO VALUES ONLY, not clinical guidance. They only
// fill the form: the clinician still proposes, the caregiver confirms, and the
// pump checks its own limits.

import { escapeHtml, ml, mlHr, simLabelHtml, t } from "/shared/core.js";
import { api, isNotAvailable } from "/shared/data.js";

const $ = (id) => document.getElementById(id);

// The hub sends profile names as data (English). Known demo names get translated.
const KNOWN_NAMES = {
  "Overnight continuous": "profile_overnight",
  "Daytime bolus": "profile_day_bolus",
  "School day": "profile_school",
};
const nameOf = (p) => (KNOWN_NAMES[p.name] ? t(KNOWN_NAMES[p.name]) : p.name);

export function initProfiles() {
  let profiles = [];
  let message = "loading";
  let selected = null;
  let modified = false;

  function paintStatus() {
    $("profile-status").textContent = modified ? t("profile_modified")
      : selected ? t("profile_applied", { name: nameOf(selected) }) : "";
  }

  function paint() {
    $("profile-buttons").innerHTML = profiles.length
      ? profiles.map((p, i) =>
        `<button type="button" class="btn btn-small profile-choice" data-profile="${i}">` +
        `<strong>${escapeHtml(nameOf(p))}</strong><span>${escapeHtml(t("profile_values", {
          mode: t(`mode_${p.mode}`), rate: mlHr(p.rate_ml_hr), volume: ml(p.volume_ml),
        }))}</span>${p.simulated ? simLabelHtml() : ""}</button>`).join("")
      : `<p class="empty">${escapeHtml(t(message))}</p>`;
    paintStatus();
  }

  $("profile-buttons").addEventListener("click", (ev) => {
    const button = ev.target.closest("[data-profile]");
    if (!button) return;
    const p = profiles[Number(button.dataset.profile)];
    $("propose-form").elements.mode.value = p.mode;
    $("rate").value = String(p.rate_ml_hr);
    $("volume").value = String(p.volume_ml);
    selected = p;
    modified = false;
    paintStatus();
    $("rate").focus();
  });

  $("propose-form").addEventListener("input", () => {
    if (selected) { modified = true; paintStatus(); }
  });
  $("propose-form").addEventListener("reset", () => {
    selected = null;
    modified = false;
    paintStatus();
  });

  paint();
  return {
    async setPatient(patientId) {
      try {
        profiles = patientId ? await api.profiles(patientId) : [];
        message = patientId ? "profiles_none" : "clin_unavailable";
      } catch (err) {
        profiles = [];
        message = isNotAvailable(err) ? "clin_unavailable" : "error_generic";
      }
      paint();
    },
    rerender: paint,
  };
}
