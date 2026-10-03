// Shared helpers for both apps: strings, hub API, live stream, icons, honesty labels.
// Plain ES modules, no build step, no CDN.

import en from "./strings.en.js";

// ---- Strings ---------------------------------------------------------------

const LANGS = { en };
let strings = en;

export async function loadLanguage(lang) {
  if (!LANGS[lang]) {
    try {
      LANGS[lang] = (await import(`./strings.${lang}.js`)).default;
    } catch {
      lang = "en";
    }
  }
  strings = LANGS[lang];
  document.documentElement.lang = strings.lang;
  applyStrings();
  return strings.lang;
}

/** Look up a string and fill {placeholders}. Falls back to English, then the key. */
export function t(key, vars = {}) {
  const raw = strings[key] ?? en[key] ?? key;
  return raw.replace(/\{(\w+)\}/g, (m, name) => (name in vars ? String(vars[name]) : m));
}

export function userName(id) {
  return (strings.users && strings.users[id]) || en.users[id] || id;
}

/** Fill every element marked data-i18n="key" (text) or data-i18n-attr="attr:key". */
export function applyStrings(root = document) {
  root.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.dataset.i18n);
  });
  root.querySelectorAll("[data-i18n-attr]").forEach((el) => {
    for (const pair of el.dataset.i18nAttr.split(";")) {
      const [attr, key] = pair.split(":");
      el.setAttribute(attr.trim(), t(key.trim()));
    }
  });
}

// ---- Formatting ------------------------------------------------------------

export function fmtTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleTimeString(strings.lang, { hour: "2-digit", minute: "2-digit" });
}

export function fmtNumber(n) {
  const value = Number(n) || 0;
  return value.toLocaleString(strings.lang, { maximumFractionDigits: 1 });
}

export const ml = (n) => t("unit_ml", { value: fmtNumber(n) });
export const mlHr = (n) => t("unit_ml_hr", { value: fmtNumber(n) });

// ---- Icons (inline SVG, decorative: always next to text) --------------------

const PATHS = {
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  send: '<path d="M4 12l16-8-6 16-2.5-6.5z"/><path d="M11.5 13.5L20 4"/>',
  x: '<path d="M6 6l12 12M18 6L6 18"/>',
  alert: '<path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18v.5"/>',
  wifi: '<path d="M2.5 9a14 14 0 0119 0M5.5 12.5a9.5 9.5 0 0113 0M8.5 16a5 5 0 017 0"/><circle cx="12" cy="19.5" r="1"/>',
  wifiOff: '<path d="M3 3l18 18"/><path d="M8.5 16a5 5 0 017 0M5.5 12.5a9.5 9.5 0 014-2.3M2.5 9a14 14 0 015-3M14 10.3a9.5 9.5 0 014.5 2.2M17 6.3a14 14 0 014.5 2.7"/><circle cx="12" cy="19.5" r="1"/>',
  play: '<path d="M7 4.5v15l12-7.5z"/>',
  pause: '<path d="M8 5v14M16 5v14"/>',
  drop: '<path d="M12 3s6 7 6 11a6 6 0 01-12 0c0-4 6-11 6-11z"/>',
  replace: '<path d="M4 8h13l-3-3M20 16H7l3 3"/>',
  flask: '<path d="M9 3h6M10 3v6l-5 9a2 2 0 002 3h10a2 2 0 002-3l-5-9V3"/><path d="M7.5 15h9"/>',
  moon: '<path d="M20 14.5A8 8 0 019.5 4a8 8 0 1010.5 10.5z"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/>',
};

export function icon(name) {
  return (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" ' +
    `stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${PATHS[name] || ""}</svg>`
  );
}

// ---- Prescription chip (S5: exactly what the hub reports) --------------------

const CHIP = {
  proposed: { tone: "neutral", icon: "clock" },
  confirmed: { tone: "neutral", icon: "clock" },
  sent: { tone: "info", icon: "send" },
  active: { tone: "ok", icon: "check" },
  rejected: { tone: "danger", icon: "x" },
  superseded: { tone: "neutral", icon: "replace" },
};

/**
 * Label and detail for a prescription state. `availability` lets "Sent" say the
 * pump is offline (FR-10). Never guesses ahead of the hub.
 */
export function chipInfo(rx, availability) {
  const spec = CHIP[rx.state] || CHIP.proposed;
  let label = t(`rx_${rx.state}`);
  let detail = t(`rx_${rx.state}_detail`);
  if (rx.state === "rejected") {
    label = t("rx_rejected_reason", { reason: t(`reason_${rx.reject_reason}`) });
    detail = "";
  }
  if (rx.state === "sent" && availability && !availability.online) {
    label = t("rx_sent_offline", { time: fmtTime(availability.last_seen_at) || "?" });
  }
  return { ...spec, label, detail };
}

export function chipHtml(rx, availability) {
  const c = chipInfo(rx, availability);
  return `<span class="chip tone-${c.tone}">${icon(c.icon)}<span>${escapeHtml(c.label)}</span></span>`;
}

// ---- Honesty components (S8, NFR-H1) ----------------------------------------

export function simLabelHtml() {
  return `<span class="sim-label">${icon("flask")}<span>${escapeHtml(t("simulated_data"))}</span></span>`;
}

export function renderFooter(el) {
  el.innerHTML =
    `<p><strong>${escapeHtml(t("prototype_footer"))}</strong> ` +
    `${escapeHtml(t("prototype_footer_detail"))}</p>`;
}

export function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);
}
