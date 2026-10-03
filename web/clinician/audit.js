// Portal: audit trail with caregiver roles (FR-23, FR-29). Read-only: the hub's
// audit log is append-only (S7). Refetched whenever a prescription changes.

import { escapeHtml, fmtDateTime, t, userName } from "/shared/core.js";
import { api, isNotAvailable } from "/shared/data.js";
import { setHtml } from "/shared/ui.js";

const $ = (id) => document.getElementById(id);
const ROLE_KEYS = {
  clinician: "role_clinician", parent: "role_parent", school_nurse: "role_school_nurse",
  system: "role_system", hub: "role_system", pump: "role_pump",
};

const label = (prefix, value, fallback) => {
  const key = `${prefix}${value}`;
  const text = t(key);
  return text === key ? fallback ?? String(value ?? "") : text;
};

export function initAudit(store) {
  const pumpId = store.state.pumpId;
  let rows = null;
  let error = null;
  let signature = null;
  let timer = null;

  function render() {
    if (error) {
      setHtml($("audit"), `<p class="empty">${escapeHtml(t(error))}</p>`, { fade: false });
      return;
    }
    if (!rows) {
      setHtml($("audit"), `<p class="empty">${escapeHtml(t("loading"))}</p>`, { fade: false });
      return;
    }
    if (!rows.length) {
      setHtml($("audit"), `<p class="empty">${escapeHtml(t("audit_empty"))}</p>`, { fade: false });
      return;
    }
    const body = rows.map((r) => {
      const role = ROLE_KEYS[r.actor_role] ? t(ROLE_KEYS[r.actor_role]) : r.actor_role;
      const who = t("audit_who", { name: userName(r.actor), role });
      const version = String(r.entity_id || "").split("/").pop();
      return `<tr><th scope="row"><time datetime="${escapeHtml(r.at)}">${escapeHtml(fmtDateTime(r.at))}</time></th>` +
        `<td>${escapeHtml(who)}</td><td>${escapeHtml(label("action_", r.action, r.action))}</td>` +
        `<td>${escapeHtml(version)}</td></tr>`;
    }).join("");
    setHtml($("audit"),
      `<table class="data"><thead><tr><th scope="col">${escapeHtml(t("audit_col_when"))}</th>` +
      `<th scope="col">${escapeHtml(t("audit_col_who"))}</th><th scope="col">${escapeHtml(t("audit_col_what"))}</th>` +
      `<th scope="col">${escapeHtml(t("audit_col_version"))}</th></tr></thead><tbody>${body}</tbody></table>`,
      { fade: false });
  }

  async function load() {
    try {
      rows = await api.audit(pumpId);
      error = null;
    } catch (err) {
      error = isNotAvailable(err) ? "clin_unavailable" : "error_generic";
    }
    render();
  }

  store.subscribe((state) => {
    const sig = Object.values(state.prescriptions).map((r) => `${r.version}:${r.state}`).join(",");
    if (sig !== signature) {
      signature = sig;
      clearTimeout(timer);
      timer = setTimeout(load, 300); // let a burst of lifecycle events settle
    }
  });
  return { rerender: render };
}
