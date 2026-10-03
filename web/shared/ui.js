// Small rendering helpers shared by both apps.

import { escapeHtml, fmtTime, icon, t } from "./core.js";

/** Set innerHTML only when it changes, so aria-live does not re-announce every tick. */
export function setHtml(el, html, { fade = true } = {}) {
  if (el.dataset.html === html) return false;
  el.dataset.html = html;
  el.innerHTML = html;
  if (fade) {
    el.classList.remove("fade");
    void el.offsetWidth; // restart the short fade
    el.classList.add("fade");
  }
  return true;
}

export function setText(el, text) {
  if (el.textContent !== text) el.textContent = text;
}

/** True once the hub has relayed at least one real status from the pump. */
export function hasStatus(state) {
  return !!(state.status && state.status.received_at && state.status.state);
}

/**
 * Connection banner plus a separate polite live region that speaks only when the
 * kind of connection changes (not every minute as the time ticks).
 */
export function renderConnection(bannerEl, liveEl, state) {
  const time = fmtTime(state.lastUpdateAt);
  let tone, ic, title, body = "";
  if (state.stream === "connecting") {
    tone = "neutral"; ic = "clock"; title = t("connecting");
  } else if (state.stream === "lost") {
    // The stream to the hub dropped. data.js keeps retrying in the background.
    tone = "warn"; ic = "wifiOff";
    title = time ? t("offline_last_update", { time }) : t("offline_no_update");
    body = t("hub_lost");
  } else if (!state.availability.online) {
    tone = "warn"; ic = "wifiOff";
    const since = fmtTime(state.availability.last_seen_at);
    title = since ? t("pump_offline_since", { time: since }) : t("pump_offline");
    body = t("pump_offline_body");
  } else {
    tone = "ok"; ic = "wifi";
    title = time ? t("online_last_update", { time }) : t("pump_online");
  }

  const kind = state.stream === "open" ? (state.availability.online ? "online" : "offline")
    : state.stream;
  if (liveEl.dataset.kind !== kind) {
    liveEl.dataset.kind = kind;
    // Quiet on first load while connecting; speak every later change.
    if (kind !== "connecting") liveEl.textContent = body ? `${title}. ${body}` : title;
  }

  bannerEl.className = `banner conn tone-${tone}`;
  setHtml(bannerEl, `${icon(ic)}<span><strong>${escapeHtml(title)}</strong>` +
    (body ? `<span class="conn-body">${escapeHtml(body)}</span>` : "") + "</span>");
}

/** Read the caregiver id this phone confirms as. */
export function savedCaregiver() {
  try {
    const id = localStorage.getItem("sp-caregiver");
    if (id === "care-01" || id === "care-02") return id;
  } catch {
    /* storage blocked */
  }
  return "care-01";
}

export function saveCaregiver(id) {
  try {
    localStorage.setItem("sp-caregiver", id);
  } catch {
    /* storage blocked: the choice lasts for this page only */
  }
}
