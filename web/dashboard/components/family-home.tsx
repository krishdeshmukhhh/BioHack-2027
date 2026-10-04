"use client";
import { Bell, ChevronRight, Home, ClipboardCheck, FlaskConical } from "lucide-react";
import { motion } from "framer-motion";
import { useLocale } from "@/lib/locale";
import type { Patient, Pump } from "@/lib/pump";
import { FeedGauge } from "./primitives";

export function FamilyHome({ pump, patient, patients, choose, inspect }: {
  pump: Pump; patient?: Patient; patients: Patient[]; choose: (id: string) => void; inspect: () => void;
}) {
  const { t, number } = useLocale();
  const pending = Object.values(pump.prescriptions).filter((rx) => rx.state === "proposed").length;
  const alarms = pump.alerts.filter((alert) => alert.active).length;
  const status = pump.status;
  return <div className="family-home local-scroll min-h-0 flex-1 overflow-y-auto px-6 pb-6">
    {/* S8: every screen with simulated data says so, readable on a phone. */}
    <p className="mb-4 inline-flex items-center gap-2 rounded-full border border-line px-4 py-2 text-lg font-semibold text-ink"><FlaskConical size={18} aria-hidden="true" />{t("simulated_data")}</p>
    <label className="mb-5 block text-xs text-muted">{t("demo_child")}
      <select className="input mt-2 text-sm!" value={pump.pumpId} onChange={(event) => choose(event.target.value)}>
        {!patients.length && <option value={pump.pumpId}>{pump.pumpId}</option>}
        {patients.map((child) => <option key={child.id} value={child.pump_id}>{child.display_name}</option>)}
      </select>
    </label>
    <motion.div layout className="home-feed grid items-center gap-6 rounded-2xl border border-line bg-panel p-6">
      <div className="min-w-0"><p className="kicker flex items-center gap-2"><Home size={15} />{t("home_feed")}</p>
        <h2 className="mt-3 text-2xl font-semibold tracking-tight">{patient?.display_name || pump.pumpId}</h2>
        <p className="mt-2 text-sm text-muted">{t("family_home_hint")}</p>
        <span className="mt-5 inline-block rounded-full bg-tint px-3 py-1 text-xs text-accent">{status ? t(`state_${status.state}`) : t("connecting")}</span>
        <dl className="mt-6 grid grid-cols-2 gap-4"><div><dt className="text-xs text-muted">{t("family_rate_now")}</dt><dd className="mt-2 text-xl">{status ? number(status.rate_ml_hr) : "—"}<span className="ml-1 text-xs text-muted">mL/hr</span></dd></div><div><dt className="text-xs text-muted">{t("remaining")}</dt><dd className="mt-2 text-xl">{status ? number(Math.max(0, status.target_ml - status.delivered_ml)) : "—"}<span className="ml-1 text-xs text-muted">mL</span></dd></div></dl>
      </div>
      <div className="home-progress">{status ? <FeedGauge delivered={status.delivered_ml} target={status.target_ml} /> : <p role="status" className="text-center text-muted">{t("loading")}</p>}<p className="text-center text-xs text-muted">{status ? `${number(status.delivered_ml)} / ${number(status.target_ml)} mL` : "—"}</p></div>
    </motion.div>
    <div className="mt-5 grid gap-3"><button className="home-action flex items-center gap-4 rounded-xl border border-line p-4 text-left" onClick={inspect}><ClipboardCheck className="shrink-0 text-accent" size={22} /><span className="flex-1"><strong className="block text-sm">{t("family_changes")}</strong><span className="mt-1 block text-xs text-muted">{t(pending ? "family_pending" : "family_no_pending", { count: pending })}</span></span><ChevronRight size={18} /></button>
      <button className="home-action flex items-center gap-4 rounded-xl border border-line p-4 text-left" onClick={inspect}><Bell className={alarms ? "shrink-0 text-danger" : "shrink-0 text-accent"} size={22} /><span className="flex-1"><strong className="block text-sm">{t("current_alerts")}</strong><span className={`mt-1 block text-xs ${alarms ? "text-danger" : "text-muted"}`}>{t(alarms ? "active_alarm" : "all_clear")}</span></span><ChevronRight size={18} /></button></div>
  </div>;
}
