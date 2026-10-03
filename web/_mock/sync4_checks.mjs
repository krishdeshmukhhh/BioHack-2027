// Regression checks for web behavior without a browser or third-party packages.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import vm from "node:vm";

const root = new URL("../", import.meta.url);
const elements = new Map();
function element(id) {
  if (!elements.has(id)) elements.set(id, {
    dataset: {}, textContent: "", innerHTML: "", hidden: false, clientWidth: 320,
    handlers: {}, classList: { remove() {}, add() {} },
    addEventListener(event, fn) { this.handlers[event] = fn; },
    setAttribute(key, value) { this[key] = value; },
    focus() { document.activeElement = this; },
  });
  return elements.get(id);
}
const ranges = ["24h", "7d", "30d"].map((range) => {
  const el = element(range);
  el.dataset.range = range;
  return el;
});
const document = {
  documentElement: {}, activeElement: null,
  getElementById: element,
  querySelectorAll(selector) { return selector === "#ranges .range" ? ranges : []; },
};
const scheduled = [];
const context = vm.createContext({
  document, console,
  localStorage: {
    getItem() { throw new Error("Storage blocked"); },
    setItem() { throw new Error("Storage blocked"); },
  },
  ResizeObserver: class { observe() {} },
  setTimeout(fn) { scheduled.push(fn); return scheduled.length; },
  clearTimeout() {},
});
const pending = [];
let auditCalls = 0;
const api = {
  daily(patient, days) {
    return new Promise((resolve) => pending.push({ patient, days, resolve }));
  },
  async audit() { auditCalls++; return []; },
  async profiles() {
    return [{ name: "School day", mode: "continuous", rate_ml_hr: 60, volume_ml: 500, simulated: true }];
  },
};
const modules = new Map();
const data = new vm.SyntheticModule(["api", "isNotAvailable"], function () {
  this.setExport("api", api);
  this.setExport("isNotAvailable", () => false);
}, { context, identifier: "shared/data.js" });
modules.set("shared/data.js", data);
async function moduleFor(id) {
  if (modules.has(id)) return modules.get(id);
  const mod = new vm.SourceTextModule(await readFile(new URL(id, root), "utf8"), {
    context, identifier: id,
    async importModuleDynamically(specifier, parent) {
      const child = await load(resolve(specifier, parent.identifier));
      return child;
    },
  });
  modules.set(id, mod);
  await mod.link((specifier, parent) => moduleFor(resolve(specifier, parent.identifier)));
  return mod;
}
function resolve(specifier, parent) {
  return specifier.startsWith("/") ? specifier.slice(1)
    : new URL(specifier, `https://web.test/${parent}`).pathname.slice(1);
}
async function load(id) {
  const mod = await moduleFor(id);
  if (mod.status === "linked") await mod.evaluate();
  return mod;
}
const tick = () => new Promise((done) => setImmediate(done));

// Storage restrictions must not change the caregiver sent with a confirmation.
const ui = (await load("shared/ui.js")).namespace;
assert.equal(ui.savedCaregiver(), "care-01");
ui.saveCaregiver("care-02");
assert.equal(ui.savedCaregiver(), "care-02");
ui.saveCaregiver("unexpected");
assert.equal(ui.savedCaregiver(), "care-02");
const settings = (await load("family/settings.js")).namespace;
settings.initSettings();
element("pref-speak").handlers.change({ target: { checked: false } });
assert.equal(settings.prefsFor("care-02").speak, false);
assert.equal(settings.prefsFor("care-01").speak, true);

// A slow 7-day response must not overwrite the selected 30-day range.
const chart = (await load("clinician/chart.js")).namespace.initChart({
  state: { history: [] }, subscribe() {},
});
chart.setPatient("patient-1");
element("30d").handlers.click();
assert.deepEqual(pending.map((r) => r.days), [7, 30]);
pending[1].resolve([{ date: "2026-10-01", delivered_ml: 300, prescribed_ml: 400, alarm_count: 1, simulated: true }]);
await tick();
assert.match(element("chart-summary").textContent, /300 mL/);
pending[0].resolve([{ date: "2026-10-01", delivered_ml: 7, prescribed_ml: 10, alarm_count: 0 }]);
await tick();
assert.match(element("chart-summary").textContent, /300 mL/);
assert.doesNotMatch(element("chart-summary").textContent, /7 mL/);

// The audit endpoint still loads when there are no prescriptions in memory.
(await load("clinician/audit.js")).namespace.initAudit({
  state: { pumpId: "pump-001" }, subscribe(fn) { fn({ prescriptions: {} }); },
});
assert.equal(scheduled.length, 1);
await scheduled[0]();
assert.equal(auditCalls, 1);
assert.match(element("audit").innerHTML, /No audit entries/);

// Profile feedback follows language switches, edits, and successful form resets.
element("propose-form").elements = { mode: { value: "" } };
const profiles = (await load("clinician/profiles.js")).namespace.initProfiles();
await profiles.setPatient("patient-1");
element("profile-buttons").handlers.click({ target: { closest: () => ({ dataset: { profile: "0" } }) } });
assert.equal(element("rate").value, "60");
const core = (await load("shared/core.js")).namespace;
await core.loadLanguage("es");
profiles.rerender();
assert.doesNotMatch(element("profile-status").textContent, /School day|Form filled/);
assert.match(element("profile-status").textContent, /Revise|Revís|Compruebe|revis|comprueb/i);
element("propose-form").handlers.input();
assert.equal(element("profile-status").textContent, core.t("profile_modified"));
element("propose-form").handlers.reset();
assert.equal(element("profile-status").textContent, "");

// Every translated entry retains the same interpolation variables.
const en = (await load("shared/strings.en.js")).namespace.default;
const es = (await load("shared/strings.es.js")).namespace.default;
assert.deepEqual(Object.keys(en).sort(), Object.keys(es).sort());
for (const key of Object.keys(en)) {
  if (typeof en[key] !== "string") continue;
  const placeholders = (s) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();
  assert.deepEqual(placeholders(en[key]), placeholders(es[key]), key);
}
console.log("Sync 4 regression checks passed");
