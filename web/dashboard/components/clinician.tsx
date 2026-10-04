"use client";
import { useState, type FormEvent } from "react";
import { Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ArrowUpRight, ClipboardList, FilePenLine, History, ListChecks } from "lucide-react";
import { useLocale } from "@/lib/locale";
import { api, errorKey, useResource, type Audit, type Daily, type Patient, type Profile, type Pump, type Summary } from "@/lib/pump";
import { Accordion, FeedGauge, RxChip, SimLabel } from "./primitives";

export function ClinicianView({ pump, selectPump }: { pump: Pump; selectPump: (id: string) => void }) {
  const { t, date, number, user } = useLocale();
  const [days, setDays] = useState(7);
  const patients = useResource<Patient[]>("/api/patients", 5000);
  const patient = patients.data?.find((p) => p.pump_id === pump.pumpId);
  const daily = useResource<Daily[]>(patient ? `/api/patients/${patient.id}/daily?days=${days}` : null);
  const profiles = useResource<Profile[]>(patient ? `/api/patients/${patient.id}/profiles` : null);
  const summary = useResource<Summary>(patient ? `/api/patients/${patient.id}/summary` : null);
  const audit = useResource<Audit[]>(`/api/pumps/${pump.pumpId}/audit`, 2000);
  const prescriptions = Object.values(pump.prescriptions).sort((a, b) => b.version - a.version);
  const [busy, setBusy] = useState(false), [error, setError] = useState(""), [submitted, setSubmitted] = useState<number | null>(null);
  const [form, setForm] = useState({ mode: "continuous", rate: "", volume: "", note: "" });
  const s = pump.status;
  async function propose(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const rate = Number(form.rate), volume = Number(form.volume);
    if (!Number.isFinite(rate) || rate <= 0 || !Number.isFinite(volume) || volume <= 0 || form.note.length > 200) { setError(t("error_invalid_input")); return; }
    setBusy(true); setError(""); setSubmitted(null);
    try {
      const rx = await api.propose(pump.pumpId, { mode: form.mode, rate_ml_hr: rate, volume_ml: volume, note: form.note, proposed_by: "clin-01" });
      setSubmitted(rx.version); setForm({ mode: "continuous", rate: "", volume: "", note: "" });
    } catch (err) { setError(t(errorKey(err))); }
    finally { setBusy(false); }
  }
  const names: Record<string, string> = { "Overnight continuous": "profile_overnight", "Daytime bolus": "profile_day_bolus", "School day": "profile_school" };
  return <div className="grid items-start gap-8 xl:grid-cols-[240px_minmax(0,1fr)] xl:gap-10">
    <aside className="min-w-0" aria-labelledby="roster-title">
      <h2 id="roster-title" className="kicker mb-4">{t("clin_patients_title")}</h2><p className="mb-5 text-sm text-muted">{t("patient_hint")}</p>
      {patients.error && <p role="status" className="text-danger">{t("patients_stale")}</p>}
      {!patients.data && <p className="text-muted">{t("loading")}</p>}
      <ul className="space-y-1">{patients.data?.map((p) => <li key={p.id}><button aria-current={p.pump_id === pump.pumpId ? "true" : undefined} onClick={() => { selectPump(p.pump_id); setSubmitted(null); setError(""); setForm({ mode: "continuous", rate: "", volume: "", note: "" }); }} className={`w-full rounded-xl px-4 py-5 text-left transition-colors ${p.pump_id === pump.pumpId ? "bg-tint" : "hover:bg-tint/60"}`}>
        <span className="flex items-start justify-between gap-3"><strong className="text-base font-semibold">{p.display_name}</strong><ArrowUpRight size={16} aria-hidden="true" className="shrink-0" /></span><span className="mt-1 block text-xs text-muted">{p.pump_id}</span>
        <span className="mt-3 flex flex-wrap gap-2">{p.exceptions.length ? p.exceptions.map((code) => <span key={code} className="text-xs font-medium text-warm">{t(`exc_${code}`)}</span>) : <span className="text-xs text-good">{t("exc_none")}</span>}</span>
        {p.simulated && <span className="mt-3 inline-flex"><SimLabel /></span>}
      </button></li>)}</ul>
    </aside>
    <div className="min-w-0">
      <div className="mb-7 border-b border-line pb-5"><p className="kicker mb-2">{t("current")}</p><h2 className="font-display text-3xl tracking-tight">{patient?.display_name || pump.pumpId}</h2></div>
      <div className="grid items-center gap-6 md:grid-cols-[220px_minmax(0,1fr)]">
        <FeedGauge delivered={s?.delivered_ml || 0} target={s?.target_ml || 0} />
        <div><p className="mb-5 text-sm font-medium" role="status">{s ? t(`state_${s.state}`) : t("unknown")}</p><dl className="grid grid-cols-2 gap-x-8 gap-y-6">
          {[{ label: t("family_rate_now"), value: s ? `${number(s.rate_ml_hr)} mL/hr` : "—" }, { label: t("clin_active_version"), value: s ? `v${s.prescription_version}` : "—" }, { label: t("family_delivered"), value: s ? `${number(s.delivered_ml)} mL` : "—" }, { label: t("chart_prescribed"), value: s ? `${number(s.target_ml)} mL` : "—" }].map((item) => <div key={item.label}><dt className="text-xs text-muted">{item.label}</dt><dd className="mt-1 text-xl font-semibold tabular-nums">{item.value}</dd></div>)}
        </dl></div>
      </div>
      <section aria-labelledby="delivery-title" className="my-8 border-y border-line py-7">
        <div className="mb-6 flex flex-wrap items-center justify-between gap-4"><h2 id="delivery-title" className="text-lg font-semibold">{t("history")}</h2><div role="group" aria-label={t("range_label")} className="flex gap-1 rounded-lg bg-tint p-1">{[7, 30].map((value) => <button key={value} aria-pressed={days === value} onClick={() => setDays(value)} className={`rounded-md px-3 text-sm ${days === value ? "bg-panel font-semibold" : "text-muted"}`}>{t(value === 7 ? "range_7d" : "range_30d")}</button>)}</div></div>
        {daily.data?.length ? <>
          <div className="h-[240px] w-full min-w-0" role="img" aria-label={t("chart_title")}><ResponsiveContainer width="100%" height="100%" minWidth={0}><ComposedChart data={daily.data} margin={{ left: 0, right: 8, top: 8, bottom: 4 }}><CartesianGrid vertical={false} stroke="var(--line)" /><XAxis dataKey="date" tickFormatter={(value: string) => value.slice(5)} tickLine={false} axisLine={false} fontSize={11} minTickGap={25} /><YAxis width={42} tickLine={false} axisLine={false} fontSize={11} /><Tooltip contentStyle={{ background: "var(--panel)", borderColor: "var(--line)", color: "var(--ink)", fontSize: 14 }} /><Area name={t("chart_delivered")} type="monotone" dataKey="delivered_ml" stroke="var(--accent)" strokeWidth={2.5} fill="var(--tint)" isAnimationActive={false} /><Line name={t("chart_prescribed")} dataKey="prescribed_ml" stroke="var(--warm)" strokeDasharray="5 4" dot={false} isAnimationActive={false} /></ComposedChart></ResponsiveContainer></div>
          <div className="mt-4 flex flex-wrap items-center gap-5 text-xs text-muted"><span className="flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-accent" />{t("chart_delivered")}</span><span className="flex items-center gap-2"><span className="h-0 w-4 border-t border-dashed border-warm" />{t("chart_prescribed")}</span>{daily.data.some((r) => r.simulated) && <SimLabel />}</div>
          <details className="mt-4"><summary className="py-3 text-sm text-accent">{t("chart_show_table")}</summary><div className="table-scroll" tabIndex={0} role="region" aria-label={t("chart_title")}><table><thead><tr><th>{t("chart_col_date")}</th><th>{t("chart_delivered")}</th><th>{t("chart_prescribed")}</th><th>{t("chart_col_alarms")}</th></tr></thead><tbody>{daily.data.map((r) => <tr key={r.date}><th scope="row">{r.date}</th><td>{number(r.delivered_ml)} mL</td><td>{number(r.prescribed_ml)} mL</td><td>{r.alarm_count}</td></tr>)}</tbody></table></div></details>
        </> : <p className="text-muted">{t(daily.error ? "clin_unavailable" : daily.data ? "chart_no_data" : "loading")}</p>}
      </section>
      <div className="grid items-start gap-6 xl:grid-cols-2">
        <div>
          <Accordion title={t("new_proposal")} subtitle={t("clin_propose_intro")} icon={<FilePenLine size={21} />} defaultOpen>
            {profiles.data?.length ? <div className="mb-5"><h3 className="mb-3 text-sm font-medium">{t("profiles_title")}</h3><div className="flex flex-wrap gap-2">{profiles.data.map((p) => <button className="button text-sm!" key={p.id} onClick={() => setForm({ ...form, mode: p.mode, rate: String(p.rate_ml_hr), volume: String(p.volume_ml) })}>{names[p.name] ? t(names[p.name]) : p.name}</button>)}</div><p className="mt-2 text-xs text-muted">{t("profiles_intro")}</p></div> : null}
            <form onSubmit={propose} className="space-y-4">
              <label className="block text-sm font-medium" htmlFor="mode">{t("field_mode")}<select className="input mt-2" id="mode" value={form.mode} onChange={(event) => setForm({ ...form, mode: event.target.value })}><option value="continuous">{t("mode_continuous")}</option><option value="bolus">{t("mode_bolus")}</option></select></label>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2"><label className="block text-sm font-medium" htmlFor="rate">{t("field_rate")}<input id="rate" required type="number" step="any" inputMode="decimal" className="input mt-2" value={form.rate} onChange={(event) => setForm({ ...form, rate: event.target.value })} aria-describedby="rate-unit" /><span id="rate-unit" className="mt-1 block text-xs text-muted">mL/hr</span></label><label className="block text-sm font-medium" htmlFor="volume">{t("field_volume")}<input id="volume" required type="number" step="any" inputMode="decimal" className="input mt-2" value={form.volume} onChange={(event) => setForm({ ...form, volume: event.target.value })} aria-describedby="volume-unit" /><span id="volume-unit" className="mt-1 block text-xs text-muted">mL</span></label></div>
              <label className="block text-sm font-medium" htmlFor="note">{t("field_note")}<textarea className="input mt-2" id="note" maxLength={200} value={form.note} onChange={(event) => setForm({ ...form, note: event.target.value })} /></label>
              {error && <p role="alert" className="text-sm text-danger">{error}</p>}<button className="button button-primary w-full" disabled={busy}>{t(busy ? "clin_submitting" : "clin_submit")}</button>{submitted != null && <p role="status" className="text-sm text-good">{t("clin_proposed_ok", { version: submitted })}</p>}
            </form>
          </Accordion>
          <Accordion title={t("summary_title")} icon={<ListChecks size={21} />}>
            {summary.data?.days ? <div className="space-y-3 text-base"><p>{t("summary_delivered", { pct: number(summary.data.delivered_pct), days: summary.data.days })}</p><p>{t("summary_under", { count: summary.data.days_under_target })}</p><p>{t(`trend_${summary.data.trend}`)}</p>{summary.data.simulated && <SimLabel />}</div> : <p className="text-muted">{t(summary.error ? "clin_unavailable" : "summary_none")}</p>}
          </Accordion>
        </div>
        <div>
          <Accordion title={t("clin_history_title")} icon={<ClipboardList size={21} />} defaultOpen>
            <ol className="space-y-5">{prescriptions.map((rx) => <li key={rx.version} className="border-l-2 border-line pl-4"><div className="flex flex-wrap items-center justify-between gap-3"><strong className="text-base">v{rx.version}</strong><RxChip rx={rx} /></div><p className="mt-3 text-base">{number(rx.rate_ml_hr)} mL/hr · {number(rx.volume_ml)} mL</p><p className="mt-1 text-xs text-muted">{date(rx.proposed_at)}</p>{rx.reject_reason && <p className="mt-2 text-sm text-danger">{t(`reason_${rx.reject_reason}`)}</p>}</li>)}</ol>{!prescriptions.length && <p className="text-muted">{t("clin_history_empty")}</p>}
          </Accordion>
          <Accordion title={t("timeline_title")} icon={<History size={21} />}>
            <ol className="space-y-4">{pump.alerts.map((alert) => <li key={`${alert.alarm}:${alert.raised_at}`}><strong className={alert.active ? "text-danger" : "text-ink"}>{t(`alarm_${alert.alarm}`)}</strong><p className="text-xs text-muted">{date(alert.raised_at)} · {alert.active ? t("timeline_active") : t("alert_cleared")}</p>{alert.simulated && <SimLabel />}</li>)}</ol>{!pump.alerts.length && <p className="text-muted">{t("timeline_empty")}</p>}
          </Accordion>
          <Accordion title={t("audit_title")} icon={<History size={21} />}>
            {audit.data?.length ? <div className="table-scroll" tabIndex={0} role="region" aria-label={t("audit_title")}><table><thead><tr><th>{t("audit_col_when")}</th><th>{t("audit_col_who")}</th><th>{t("audit_col_what")}</th></tr></thead><tbody>{audit.data.map((r) => <tr key={r.id}><td>{date(r.at)}</td><td>{user(r.actor)}<span className="block text-xs text-muted">{t(`role_${r.actor_role === "system" ? "system" : r.actor_role}`)}</span></td><td>{t(`action_${r.action}`)}</td></tr>)}</tbody></table></div> : <p className="text-muted">{t(audit.error ? "clin_unavailable" : "audit_empty")}</p>}
          </Accordion>
        </div>
      </div>
    </div>
  </div>;
}
