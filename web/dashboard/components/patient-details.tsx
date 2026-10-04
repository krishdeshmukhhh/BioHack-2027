"use client";
import { useId, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Activity, Bell, ClipboardList, Link2, X } from "lucide-react";
import { Area, CartesianGrid, Line, ComposedChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useLocale } from "@/lib/locale";
import { useResource, type Audit, type Daily, type Patient, type Pump } from "@/lib/pump";
import { motionTokens } from "@/lib/motion";
import { Accordion, FeedGauge, RxChip } from "./primitives";
import { FamilyView } from "./family";
import { ClinicianView } from "./clinician";

type Tab = "monitor" | "care" | "orders" | "history";
function Tabs({ items, value, change, prefix }: { items: { key: string; label: string }[]; value: string; change: (key: string) => void; prefix: string }) {
  const reduced = useReducedMotion();
  return <div className="tab-bar flex shrink-0 border-b border-line" role="tablist">{items.map((item, index) => <button key={item.key} id={`${prefix}-${item.key}`} aria-controls={`${prefix}-content`} role="tab" aria-selected={value === item.key} tabIndex={value === item.key ? 0 : -1} onClick={() => change(item.key)} onKeyDown={(event) => {
    const offsets: Record<string, number> = { ArrowRight: 1, ArrowLeft: -1 };
    const target = event.key === "Home" ? 0 : event.key === "End" ? items.length - 1 : offsets[event.key] ? (index + offsets[event.key] + items.length) % items.length : null;
    if (target === null) return;
    event.preventDefault(); change(items[target].key);
    const tabs = event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>("[role=tab]"); tabs?.[target].focus();
  }} className={`relative min-w-0 flex-1 px-1 py-3 text-xs ${value === item.key ? "text-accent" : "text-muted"}`}>
    {item.label}{value === item.key && <motion.span layoutId={reduced ? undefined : `${prefix}-tab-line`} className="absolute right-3 bottom-0 left-3 h-0.5 bg-accent" />}
  </button>)}</div>;
}
export function PatientDetails({ pump, patient, defaultTab, close, selectPump }: { pump: Pump; patient?: Patient; defaultTab: Tab; close: () => void; selectPump: (id: string) => void }) {
  const { t, date, number } = useLocale();
  const reduced = useReducedMotion();
  const [tab, setTab] = useState<Tab>(defaultTab);
  const id = useId();
  const s = pump.status;
  const active = Object.values(pump.prescriptions).find((rx) => rx.state === "active");
  const alarm = pump.alerts.find((a) => a.active)?.alarm;
  return <>
    <div className="flex shrink-0 items-start justify-between gap-3 px-5 pt-5 pb-4"><div className="min-w-0"><p className="kicker mb-2">{t("selected_patient")}</p><h2 data-patient-heading tabIndex={-1} className="truncate text-lg font-semibold">{patient?.display_name || pump.pumpId}</h2><p className="mt-1 flex items-center gap-2 text-[10px] text-muted"><span className={`status-dot ${pump.online ? "bg-accent" : "bg-warm"}`} />{pump.pumpId} · {t(pump.online ? "connected" : "disconnected")}</p></div><button className="icon-button shrink-0" onClick={close} aria-label={t("close_details")}><X size={17} aria-hidden="true" /></button></div>
    <Tabs prefix={id} value={tab} change={(key) => setTab(key as Tab)} items={(["monitor", "care", "orders", "history"] as const).map((key) => ({ key, label: t(`tab_${key}`) }))} />
    {!pump.online && pump.stream !== "connecting" && <p role="status" className="shrink-0 border-b border-line px-5 py-3 text-xs text-warm">{t("data_stale")}</p>}
    <div className="local-scroll min-h-0 flex-1 overflow-x-hidden overflow-y-auto" tabIndex={0} aria-label={t(`tab_${tab}`)}>
      <AnimatePresence mode="wait" initial={false}>
        <motion.div key={tab} id={`${id}-content`} role="tabpanel" aria-labelledby={`${id}-${tab}`} className="detail-content min-w-0 p-5" initial={{ opacity: 0, y: reduced ? 0 : motionTokens.distance.sm }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: motionTokens.duration.fast }}>
          {tab === "monitor" ? <>
            <div className="flex items-center justify-between gap-3"><h3 className="text-xs font-medium text-muted">{t("feed_telemetry")}</h3><span className="text-xs text-accent">{s ? t(`state_${s.state}`) : t("unknown")}</span></div>
            <div className="monitor-gauge mx-auto my-3 w-[185px]"><FeedGauge delivered={s?.delivered_ml || 0} target={s?.target_ml || 0} /></div>
            <p className="mb-5 text-center text-xs text-muted">{s ? `${number(s.delivered_ml)} / ${number(s.target_ml)} mL` : t("unknown")}</p>
            <dl className="mb-5 grid grid-cols-2 gap-4 border-y border-line py-4"><div><dt className="text-[10px] text-muted">{t("family_rate_now")}</dt><dd className="mt-1 text-xl tabular-nums">{s ? number(s.rate_ml_hr) : "—"}<span className="ml-1 text-[10px] text-muted">mL/hr</span></dd></div><div><dt className="text-[10px] text-muted">{t("remaining")}</dt><dd className="mt-1 text-xl tabular-nums">{s ? number(Math.max(0, s.target_ml - s.delivered_ml)) : "—"}<span className="ml-1 text-[10px] text-muted">mL</span></dd></div></dl>
            {alarm && <button className="button mb-4 w-full text-danger" onClick={() => setTab("care")}><Bell size={15} />{t(`alarm_${alarm}`)}</button>}
            <Accordion title={t("feed_active")} icon={<ClipboardList size={17} />}>
              {active ? <div className="space-y-3 text-sm"><div className="flex items-center justify-between"><span>v{active.version}</span><RxChip rx={active} /></div><p>{t(`mode_${active.mode}`)} · {number(active.rate_ml_hr)} mL/hr</p><p>{number(active.volume_ml)} mL</p>{active.note && <p className="text-muted">{active.note}</p>}</div> : <p className="text-sm text-muted">{t("unknown")}</p>}
            </Accordion>
            <Accordion title={t("connection_details")} icon={<Link2 size={17} />}><dl className="space-y-3 text-xs"><div><dt className="text-muted">{t("pump_connection")}</dt><dd className="mt-1">{t(pump.online ? "connected" : "disconnected")}</dd></div><div><dt className="text-muted">{t("last_signal")}</dt><dd className="mt-1">{date(pump.lastUpdateAt)}</dd></div></dl></Accordion>
          </> : tab === "care" ? <FamilyView pump={pump} compact /> : tab === "orders" ? <ClinicianView pump={pump} selectPump={selectPump} compact /> : <PatientHistory pump={pump} patient={patient} />}
        </motion.div>
      </AnimatePresence>
    </div>
  </>;
}

function PatientHistory({ pump, patient }: { pump: Pump; patient?: Patient }) {
  const { t, date, number, user } = useLocale();
  const [section, setSection] = useState("delivery");
  const [days, setDays] = useState(7);
  const [table, setTable] = useState(false);
  const id = useId();
  const daily = useResource<Daily[]>(patient ? `/api/patients/${patient.id}/daily?days=${days}` : null);
  const audit = useResource<Audit[]>(`/api/pumps/${pump.pumpId}/audit`, 2000);
  return <div className="min-w-0"><h3 className="mb-4 flex items-center gap-2 text-sm"><Activity size={16} className="text-accent" />{t("activity_history")}</h3><Tabs prefix={id} value={section} change={setSection} items={[{ key: "delivery", label: t("delivery_tab") }, { key: "prescriptions", label: t("prescriptions_tab") }, { key: "audit", label: t("audit_tab") }]} />
    <AnimatePresence mode="wait" initial={false}><motion.div key={section} id={`${id}-content`} role="tabpanel" aria-labelledby={`${id}-${section}`} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: motionTokens.duration.fast }} className="pt-5">
      {section === "delivery" ? <>
        <div className="mb-5 flex flex-wrap items-center justify-between gap-2"><div role="group" aria-label={t("range_label")} className="flex gap-1">{[7, 30].map((value) => <button key={value} aria-pressed={days === value} onClick={() => setDays(value)} className={`rounded-md px-2 text-xs ${days === value ? "bg-tint text-accent" : "text-muted"}`}>{t(value === 7 ? "range_7d" : "range_30d")}</button>)}</div><button className="text-xs text-accent" onClick={() => setTable(!table)}>{t(table ? "show_chart" : "show_table")}</button></div>
        {!daily.data?.length ? <p className="text-sm text-muted">{t(daily.error ? "clin_unavailable" : daily.data ? "chart_no_data" : "loading")}</p> : table ? <div className="table-scroll"><table><thead><tr><th>{t("chart_col_date")}</th><th>{t("chart_delivered")}</th><th>{t("chart_prescribed")}</th></tr></thead><tbody>{daily.data.map((d) => <tr key={d.date}><td>{d.date}</td><td>{number(d.delivered_ml)}</td><td>{number(d.prescribed_ml)}</td></tr>)}</tbody></table></div> : <><div className="h-[190px] w-full" role="img" aria-label={t("chart_title")}><ResponsiveContainer width="100%" height="100%" minWidth={0}><ComposedChart data={daily.data} margin={{ left: -20, right: 4 }}><CartesianGrid vertical={false} stroke="var(--line)" /><XAxis dataKey="date" tickFormatter={(value: string) => value.slice(5)} fontSize={9} axisLine={false} tickLine={false} minTickGap={25} /><YAxis fontSize={9} axisLine={false} tickLine={false} /><Tooltip contentStyle={{ background: "var(--panel)", borderColor: "var(--line)", fontSize: 11 }} /><Area dataKey="delivered_ml" name={t("chart_delivered")} stroke="var(--accent)" fill="var(--tint)" isAnimationActive={false} /><Line dataKey="prescribed_ml" name={t("chart_prescribed")} stroke="var(--warm)" strokeDasharray="4 4" dot={false} isAnimationActive={false} /></ComposedChart></ResponsiveContainer></div><p className="mt-3 text-[10px] text-muted">{t("chart_delivered")} / {t("chart_prescribed")} · mL</p></>}
        {daily.data?.some((d) => d.simulated) && <p className="mt-3 text-[10px] text-muted">{t("simulated_data")}</p>}
      </> : section === "prescriptions" ? <ol className="space-y-5">{Object.values(pump.prescriptions).sort((a, b) => b.version - a.version).map((rx) => <li key={rx.version}><div className="flex items-center justify-between gap-2 text-xs"><strong>v{rx.version}</strong><RxChip rx={rx} /></div><p className="mt-2 text-xs">{number(rx.rate_ml_hr)} mL/hr · {number(rx.volume_ml)} mL</p><p className="mt-1 text-[10px] text-muted">{date(rx.proposed_at)}</p>{rx.reject_reason && <p className="mt-2 text-xs text-danger">{t(`reason_${rx.reject_reason}`)}</p>}</li>)}</ol> : audit.data?.length ? <ol className="space-y-4">{audit.data.map((entry) => <li key={entry.id} className="border-l border-line pl-3"><p className="text-xs">{t(`action_${entry.action}`)}</p><p className="mt-1 text-[10px] text-muted">{user(entry.actor)} · {date(entry.at)}</p></li>)}</ol> : <p className="text-xs text-muted">{t(audit.error ? "clin_unavailable" : "audit_empty")}</p>}
    </motion.div></AnimatePresence>
  </div>;
}
