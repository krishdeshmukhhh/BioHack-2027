// Family app: "Change to review" (FR-3) and the outcome of the caregiver's answer.
// Every state shown here is the state the hub reports over SSE (S5). The reply to
// the confirm call is never used to move the outcome forward.

import { chipHtml, escapeHtml, icon, ml, mlHr, t, tList, userName } from "/shared/core.js";
import { activePrescription, api, errorText, pendingProposal } from "/shared/data.js";
import { canListenOffline, listenOnce, voiceVerdict } from "/shared/speech.js";
import { setHtml, setText } from "/shared/ui.js";
import { caregiver, onSettingsChange } from "./settings.js";

const $ = (id) => document.getElementById(id);

const FIELDS = [
  { key: "mode", label: "field_mode", fmt: (v) => t(`mode_${v}`) },
  { key: "rate_ml_hr", label: "field_rate", fmt: mlHr },
  { key: "volume_ml", label: "field_volume", fmt: ml },
];

export function initReview(store) {
  const pumpId = store.state.pumpId;
  let shownVersion = null; // proposal currently on screen
  let answered = null; // {version, action} this phone answered
  let busy = false;

  const paintButtons = () => {
    $("confirm-btn").innerHTML = `${icon("check")}<span>${escapeHtml(t("review_confirm"))}</span>`;
    $("decline-btn").innerHTML = `${icon("x")}<span>${escapeHtml(t("review_decline"))}</span>`;
    $("voice-btn").textContent = t("voice_answer");
  };
  paintButtons();

  // Optional voice answer (NFR-A5): only when speech can be recognised on the
  // device. The buttons above always do the same thing.
  canListenOffline().then((ok) => ($("voice-btn").hidden = !ok));
  $("voice-btn").addEventListener("click", async () => {
    if (busy || shownVersion == null || $("voice-btn").disabled) return;
    const version = shownVersion; // answer only the change that was on screen
    const yes = tList("voice_yes_words");
    const no = tList("voice_no_words");
    $("voice-btn").disabled = true;
    $("voice-status").textContent = t("voice_listening", { yes: yes[0], no: no[0] });
    let heard = [];
    try {
      heard = await listenOnce();
    } catch {
      heard = []; // treated as "did not catch that"
    } finally {
      $("voice-btn").disabled = false;
    }
    if (answered?.version === version) return; // answered with a button meanwhile
    if (version !== shownVersion) {
      $("voice-status").textContent = t("voice_changed");
      return;
    }
    const verdict = voiceVerdict(heard, yes, no);
    if (verdict) answer(verdict, version);
    else $("voice-status").textContent = t("voice_unheard");
  });

  async function answer(action, version = shownVersion) {
    if (busy || version == null || version !== shownVersion) return;
    busy = true;
    setButtons(true, action);
    $("review-error").hidden = true;
    $("voice-status").textContent = "";
    try {
      const who = caregiver();
      if (action === "confirm") await api.confirm(pumpId, version, who);
      else await api.decline(pumpId, version, who);
      $("voice-status").textContent = "";
      answered = { version, action };
      render(store.state);
      $("outcome-title").focus(); // the buttons are gone; move focus to the result
    } catch (err) {
      $("review-error").hidden = false;
      setHtml($("review-error"), `${icon("alert")}<span>${escapeHtml(errorText(err))}</span>`);
      store.refreshLists(); // e.g. 409: someone else already answered
    } finally {
      busy = false;
      setButtons(false);
    }
  }

  function setButtons(disabled, action) {
    for (const id of ["confirm-btn", "decline-btn"]) $(id).disabled = disabled;
    const label = disabled && action === "confirm" ? t("review_working") : t("review_confirm");
    $("confirm-btn").querySelector("span").textContent = label;
  }

  $("confirm-btn").addEventListener("click", () => answer("confirm"));
  $("decline-btn").addEventListener("click", () => answer("decline"));
  $("outcome-ok").addEventListener("click", () => {
    answered = null;
    render(store.state);
    $("main").focus();
  });

  function renderProposal(state) {
    const rx = pendingProposal(state);
    const section = $("review");
    // Hide the one this phone just answered even before SSE moves it on.
    if (!rx || (answered && answered.version === rx.version)) {
      section.hidden = true;
      shownVersion = null;
      return;
    }
    if (rx.version !== shownVersion) {
      shownVersion = rx.version;
      $("review-error").hidden = true;
      $("voice-status").textContent = "";
      $("review-live").textContent = t("review_waiting");
    }
    section.hidden = false;
    const current = activePrescription(state);

    $("review-intro").textContent = t("review_intro", { clinician: userName(rx.proposed_by) });
    setText($("review-who"), t("review_confirming_as", { who: userName(caregiver()) }));
    // One block per field: label (+ Changed), then Now and New side by side.
    const rows = FIELDS.map(({ key, label, fmt }) => {
      const now = current ? fmt(current[key]) : t("clin_none");
      const next = fmt(rx[key]);
      const changed = !current || current[key] !== rx[key];
      const marker = changed
        ? `<span class="changed">${icon("info")}<span>${escapeHtml(t("review_changed"))}</span></span>`
        : `<span class="same">${escapeHtml(t("review_same"))}</span>`;
      return `<div class="cmp${changed ? " is-changed" : ""}">` +
        `<h3>${escapeHtml(t(label))} ${marker}</h3>` +
        `<p class="cmp-now"><span class="cmp-tag">${escapeHtml(t("review_now"))}</span>${escapeHtml(now)}</p>` +
        `<p class="cmp-new"><span class="cmp-tag">${escapeHtml(t("review_new"))}</span>` +
        `<strong>${escapeHtml(next)}</strong></p></div>`;
    }).join("");
    setHtml($("review-rows"), rows, { fade: false });

    const hasNote = !!(rx.note && rx.note.trim());
    $("review-note").hidden = !hasNote;
    if (hasNote) $("review-note-text").textContent = rx.note;
  }

  function outcomeText(rx) {
    switch (rx.state) {
      case "proposed":
      case "confirmed":
        return t("review_pending");
      case "sent":
        return t("review_sent");
      case "active":
        return t("review_active", { version: rx.version });
      case "rejected":
        return rx.reject_reason === "declined"
          ? t("review_declined")
          : t("review_rejected", { reason: t(`reason_${rx.reject_reason}`) });
      case "superseded":
        return t("review_superseded");
      default:
        return t("review_pending");
    }
  }

  function renderOutcome(state) {
    const section = $("outcome");
    const rx = answered && state.prescriptions[answered.version];
    if (!answered) {
      section.hidden = true;
      return;
    }
    section.hidden = false;
    // Until SSE reports a new state, the hub's last known state (proposed) shows as Pending.
    const shown = rx || { version: answered.version, state: "proposed" };
    setHtml($("outcome-body"),
      `<p>${chipHtml(shown, state.availability)}</p><p>${escapeHtml(outcomeText(shown))}</p>`);
  }

  function render(state) {
    renderProposal(state);
    renderOutcome(state);
  }

  onSettingsChange(() => {
    paintButtons();
    $("review-rows").dataset.html = ""; // force fresh copy in the new language
    render(store.state);
  });
  store.subscribe(render);
}
