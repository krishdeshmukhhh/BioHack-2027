// The one data module for both apps: hub REST calls, the SSE stream, and shared
// state that pages render from via subscribe(fn).
//
// Rules this module keeps (docs/API.md, S5):
// - Prescription states, alerts and pump status come only from the hub. This file
//   never decides that something is "active"; it stores what SSE and REST report.
// - Action calls (confirm, decline, propose) return the hub's reply, but state is
//   updated from the SSE events that follow, not from the reply.

import { t } from "./core.js";

// ---------------------------------------------------------------------------
// SWITCH TO THE REAL HUB HERE.
// false (Sync 2 onwards): talk to whoever served this page. Served by the hub on
//        the Pi, that is the real hub; opened from the mock on :8003, the mock.
// true:  always talk to web/_mock/mock_api.py on port 8003, even when the page
//        was served from somewhere else (the mock allows cross-origin calls).
export const USE_MOCK = false;
const MOCK_PORT = 8003;
// ---------------------------------------------------------------------------

export const BASE_URL = USE_MOCK
  ? `${location.protocol}//${location.hostname}:${MOCK_PORT}`
  : "";

const HISTORY_MAX = 900; // ~30 minutes of 2 s status samples
const EVENTS_MAX = 200;
const RETRY_MIN_MS = 1000;
const RETRY_MAX_MS = 10000;

// ---- REST ------------------------------------------------------------------

export class ApiError extends Error {
  constructor(code, detail, status) {
    super(detail || code);
    this.code = code;
    this.status = status;
  }
}

async function request(method, path, body) {
  let res;
  try {
    res = await fetch(BASE_URL + path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
      cache: "no-store",
    });
  } catch {
    throw new ApiError("network", "network", 0);
  }
  let data = null;
  try {
    data = await res.json();
  } catch {
    /* empty or non-JSON body */
  }
  if (!res.ok) throw new ApiError(data?.error || "generic", data?.detail, res.status);
  return data;
}

const KNOWN_ERRORS = ["invalid_input", "not_proposed", "unknown_pump", "network"];

/** True when the hub does not offer this endpoint yet (or has no such record). */
export const isNotAvailable = (err) => err?.status === 404 && err?.code !== "unknown_pump";

/** Plain-language text for an API error. Never a bare code (NFR-A4). */
export function errorText(err) {
  return KNOWN_ERRORS.includes(err?.code) ? t(`error_${err.code}`) : t("error_generic");
}

const pumpPath = (id) => `/api/pumps/${encodeURIComponent(id)}`;

export const api = {
  status: (id) => request("GET", `${pumpPath(id)}/status`),
  prescriptions: (id) => request("GET", `${pumpPath(id)}/prescriptions`),
  alerts: (id) => request("GET", `${pumpPath(id)}/alerts`),
  audit: (id) => request("GET", `${pumpPath(id)}/audit`),
  patients: () => request("GET", "/api/patients"),
  daily: (patientId, days = 30) =>
    request("GET", `/api/patients/${encodeURIComponent(patientId)}/daily?days=${days}`),
  propose: (id, body) => request("POST", `${pumpPath(id)}/prescriptions`, body),
  confirm: (id, version, confirmedBy) =>
    request("POST", `${pumpPath(id)}/prescriptions/${version}/confirm`, { confirmed_by: confirmedBy }),
  decline: (id, version, declinedBy, reason) =>
    request("POST", `${pumpPath(id)}/prescriptions/${version}/decline`, {
      declined_by: declinedBy,
      ...(reason ? { reason } : {}),
    }),
};

/** Pump id from ?pump=, default pump-001 (the demo pump). */
export function pumpIdFromUrl() {
  const id = new URLSearchParams(location.search).get("pump");
  return id && /^[\w-]{1,64}$/.test(id) ? id : "pump-001";
}

// ---- Shared live state --------------------------------------------------------

/**
 * One store per pump. state:
 *   pumpId
 *   stream:        "connecting" | "open" | "lost"
 *   status:        latest PumpStatus, or null
 *   history:       rolling [{at, state, rate_ml_hr, delivered_ml, target_ml}]
 *   availability:  {online, last_seen_at} as the hub reports it
 *   lastUpdateAt:  ISO time of the last thing heard from the hub about this pump
 *   prescriptions: {version: Prescription}
 *   alerts:        [Alert], active first
 *   events:        rolling raw pump events, newest first
 *   online:        derived: stream open AND hub says the pump is online
 */
export function createPumpStore(pumpId) {
  const state = {
    pumpId,
    stream: "connecting",
    status: null,
    history: [],
    availability: { online: false, last_seen_at: null },
    lastUpdateAt: null,
    prescriptions: {},
    alerts: [],
    events: [],
    online: false,
  };
  const listeners = new Set();
  let queued = false;
  let es = null;
  let retryMs = RETRY_MIN_MS;

  function notify() {
    state.online = state.stream === "open" && !!state.availability.online;
    if (queued) return;
    queued = true;
    queueMicrotask(() => {
      queued = false;
      for (const fn of listeners) fn(state);
    });
  }

  function putPrescription(rx) {
    state.prescriptions[rx.version] = rx;
  }

  function putAlert(alert) {
    const i = state.alerts.findIndex(
      (a) => a.alarm === alert.alarm && a.raised_at === alert.raised_at,
    );
    if (i >= 0) state.alerts[i] = alert;
    else state.alerts.unshift(alert);
    state.alerts.sort((a, b) => Number(b.active) - Number(a.active));
  }

  function touch(iso) {
    if (iso && (!state.lastUpdateAt || iso > state.lastUpdateAt)) state.lastUpdateAt = iso;
  }

  const handlers = {
    status(s) {
      state.status = s;
      touch(s.received_at);
      if (s.received_at) {
        state.history.push({
          at: s.received_at, state: s.state, rate_ml_hr: s.rate_ml_hr,
          delivered_ml: s.delivered_ml, target_ml: s.target_ml,
        });
        if (state.history.length > HISTORY_MAX) state.history.shift();
      }
    },
    availability(a) {
      state.availability = { online: !!a.online, last_seen_at: a.last_seen_at };
      touch(a.last_seen_at);
    },
    prescription(rx) {
      putPrescription(rx);
    },
    alert(a) {
      putAlert(a);
    },
    pump_event(e) {
      state.events.unshift(e);
      if (state.events.length > EVENTS_MAX) state.events.pop();
      touch(e.received_at);
    },
  };

  // Lists the snapshot does not cover (final prescription versions, cleared alerts).
  async function refreshLists() {
    try {
      const [rxs, alerts] = await Promise.all([api.prescriptions(pumpId), api.alerts(pumpId)]);
      // SSE may have delivered newer states while this was in flight: keep those.
      for (const rx of rxs) {
        const have = state.prescriptions[rx.version];
        if (!have || rank(rx.state) >= rank(have.state)) putPrescription(rx);
      }
      for (const a of alerts) putAlert(a);
      notify();
    } catch (err) {
      console.warn("could not load lists", err);
    }
  }

  function connect() {
    if (es) es.close();
    const me = (es = new EventSource(`${BASE_URL}${pumpPath(pumpId)}/stream`));
    const current = () => me === es; // ignore anything from a replaced connection

    for (const [name, fn] of Object.entries(handlers)) {
      me.addEventListener(name, (ev) => {
        if (!current()) return;
        try {
          fn(JSON.parse(ev.data));
          state.stream = "open"; // data arriving proves the stream is up
          notify();
        } catch (e) {
          console.warn("bad SSE payload", name, e);
        }
      });
    }
    // Each open brings a fresh snapshot from the hub.
    me.addEventListener("open", () => {
      if (!current()) return;
      retryMs = RETRY_MIN_MS;
      state.stream = "open";
      notify();
      refreshLists();
    });
    me.addEventListener("error", () => {
      if (!current()) return;
      state.stream = "lost";
      notify();
      // EventSource retries a dropped stream by itself, but gives up for good
      // (CLOSED) if the hub refuses the connection, e.g. while it restarts.
      if (me.readyState === EventSource.CLOSED) {
        setTimeout(() => current() && connect(), retryMs);
        retryMs = Math.min(retryMs * 2, RETRY_MAX_MS);
      }
    });
  }

  return {
    state,
    start() {
      if (!es) connect();
      return this;
    },
    subscribe(fn) {
      listeners.add(fn);
      fn(state);
      return () => listeners.delete(fn);
    },
    refreshLists,
    /** Re-run every subscriber, e.g. after a language switch. */
    rerender: notify,
  };
}

// Lifecycle order, for merging REST and SSE copies only. Never used to set a state.
const ORDER = ["proposed", "confirmed", "sent", "active", "rejected", "superseded"];
function rank(s) {
  return s === "active" || s === "rejected" || s === "superseded" ? 3 : ORDER.indexOf(s);
}

// ---- Selectors (read-only views over the state) ------------------------------

const byVersionDesc = (a, b) => b.version - a.version;

export function prescriptionList(state) {
  return Object.values(state.prescriptions).sort(byVersionDesc);
}

/** The version the hub says is active on the pump, or null. */
export function activePrescription(state) {
  return prescriptionList(state).find((rx) => rx.state === "active") || null;
}

/** The newest proposal waiting for a caregiver, or null. */
export function pendingProposal(state) {
  return prescriptionList(state).find((rx) => rx.state === "proposed") || null;
}

export function activeAlerts(state) {
  return state.alerts.filter((a) => a.active);
}

/**
 * The alarm to show now: the hub's newest active Alert, else the status alarm
 * field (for a hub without Alerts). If the hub already reported that alarm as
 * cleared, a status sent a moment earlier must not bring it back.
 */
export function currentAlarm(state) {
  const alert = activeAlerts(state)[0];
  if (alert) return { alarm: alert.alarm, since: alert.raised_at };
  const s = state.status;
  if (!s?.alarm || !s.received_at) return null;
  if (state.alerts.some((a) => a.alarm === s.alarm && !a.active)) return null;
  return { alarm: s.alarm, since: null };
}
