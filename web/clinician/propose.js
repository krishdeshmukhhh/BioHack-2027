// Portal: propose a prescription (FR-1, FR-2).
// SHAPE ONLY: required fields, numbers greater than 0, note length. There is
// deliberately NO hard-limit check here (S1 lives in the pump), so the demo can
// show the pump refusing an out-of-range change.

import { escapeHtml, icon, t } from "/shared/core.js";
import { api, errorText } from "/shared/data.js";
import { setHtml } from "/shared/ui.js";

const $ = (id) => document.getElementById(id);
const NOTE_MAX = 200; // protocol field length (prescription.schema.json), not a clinical limit
const CLINICIAN = "clin-01";

function positiveNumber(raw) {
  if (raw.trim() === "") return { error: "val_required" };
  const value = Number(raw);
  if (!Number.isFinite(value) || value <= 0) return { error: "val_positive" };
  return { value };
}

function showFieldError(field, key) {
  const input = $(field);
  const out = $(`${field}-error`);
  if (key) {
    input.setAttribute("aria-invalid", "true");
    out.hidden = false;
    out.innerHTML = `${icon("alert")}<span>${escapeHtml(t(key))}</span>`;
  } else {
    input.removeAttribute("aria-invalid");
    out.hidden = true;
    out.textContent = "";
  }
}

export function initPropose(pumpId) {
  const form = $("propose-form");
  const button = $("propose-btn");
  const note = $("note");
  let busy = false;

  const setButton = (working) => {
    button.disabled = working;
    button.innerHTML = `${icon("send")}<span>${escapeHtml(t(working ? "clin_submitting" : "clin_submit"))}</span>`;
  };
  setButton(false);

  const updateCounter = () => {
    $("note-hint").textContent = t("clin_note_hint", { left: NOTE_MAX - note.value.length });
  };
  note.addEventListener("input", updateCounter);
  updateCounter();

  function validate() {
    const problems = [];
    const rate = positiveNumber($("rate").value);
    const volume = positiveNumber($("volume").value);
    const mode = form.elements.mode.value;
    showFieldError("rate", rate.error);
    showFieldError("volume", volume.error);
    const noteError = note.value.length > NOTE_MAX ? "val_note_long" : null;
    showFieldError("note", noteError);
    if (rate.error) problems.push({ field: "rate", label: "field_rate", error: rate.error });
    if (volume.error) problems.push({ field: "volume", label: "field_volume", error: volume.error });
    if (noteError) problems.push({ field: "note", label: "field_note", error: noteError });
    if (mode !== "continuous" && mode !== "bolus") {
      problems.push({ field: "propose-form", label: "field_mode", error: "val_mode" });
    }
    return {
      problems,
      body: { mode, rate_ml_hr: rate.value, volume_ml: volume.value, note: note.value.trim(),
        proposed_by: CLINICIAN },
    };
  }

  function showSummary(problems) {
    const box = $("form-errors");
    if (!problems.length) {
      box.hidden = true;
      return;
    }
    const items = problems.map((p) =>
      `<li><a href="#${p.field}">${escapeHtml(t(p.label))}: ${escapeHtml(t(p.error))}</a></li>`).join("");
    box.innerHTML = `${icon("alert")}<div><strong>${escapeHtml(t("clin_form_errors"))}</strong>` +
      `<p>${escapeHtml(t("val_fix", { count: problems.length }))}</p><ul>${items}</ul></div>`;
    box.hidden = false;
    box.focus();
  }

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    if (busy) return;
    const result = $("propose-result");
    result.hidden = true;
    const { problems, body } = validate();
    showSummary(problems);
    if (problems.length) return;

    busy = true;
    setButton(true);
    try {
      // The reply is only used for the confirmation message. The chip in the
      // list updates from the SSE "prescription" event, never from this reply.
      const rx = await api.propose(pumpId, body);
      result.className = "notice tone-text-ok";
      setHtml(result, `${icon("check")}<span>${escapeHtml(t("clin_proposed_ok", { version: rx.version }))}</span>`);
      form.reset();
      updateCounter();
    } catch (err) {
      result.className = "notice tone-text-danger";
      setHtml(result, `${icon("alert")}<span>${escapeHtml(errorText(err))}</span>`);
    } finally {
      result.hidden = false;
      busy = false;
      setButton(false);
    }
  });

  return {
    rerender() {
      setButton(busy);
      updateCounter();
      if (!$("form-errors").hidden) validate(); // re-word any field errors
    },
  };
}
