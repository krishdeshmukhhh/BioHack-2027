"use client";
import { useEffect, useRef, useState } from "react";
import { Bell, Check, ChevronRight, CircleAlert, FileCheck, Settings2, Volume2 } from "lucide-react";
import { useLocale } from "@/lib/locale";
import { api, type Pump } from "@/lib/pump";
import { Accordion, FeedGauge, RxChip } from "./primitives";

export function FamilyView({ pump }: { pump: Pump }) {
  const { t, list, user, number, lang } = useLocale();
  const s = pump.status;
  const delivered = s?.delivered_ml || 0, target = s?.target_ml || 0;
  const prescriptions = Object.values(pump.prescriptions).sort((a, b) => b.version - a.version);
  const proposal = prescriptions.find((rx) => rx.state === "proposed");
  const active = prescriptions.find((rx) => rx.state === "active");
  const [caregiver, setCaregiver] = useState("care-01");
  const [prefs, setPrefs] = useState({ vibrate: true, sound: true, speak: true });
  const [enabled, setEnabled] = useState(false);
  const [ack, setAck] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [answered, setAnswered] = useState<number | null>(null);
  const outcome = useRef<HTMLDivElement>(null);
  const audio = useRef<AudioContext | null>(null);
  const alarm = pump.alerts.find((a) => a.active)?.alarm || (s?.alarm && !pump.alerts.some((a) => a.alarm === s.alarm && !a.active) ? s.alarm : null);
  const alarmKey = alarm ? `${alarm}:${pump.alerts.find((a) => a.active)?.raised_at || ""}` : "";
  const latest = answered == null ? null : pump.prescriptions[answered];
  useEffect(() => { if (answered != null) outcome.current?.focus(); }, [answered]);
  useEffect(() => {
    try { const saved = localStorage.getItem("sp-caregiver"); if (saved === "care-01" || saved === "care-02") setCaregiver(saved); } catch { /* session only */ }
  }, []);
  useEffect(() => {
    const defaults = { vibrate: true, sound: true, speak: true };
    try { setPrefs({ ...defaults, ...JSON.parse(localStorage.getItem(`sp-prefs-${caregiver}`) || "{}") }); } catch { setPrefs(defaults); }
  }, [caregiver]);
  useEffect(() => { setAnswered(null); setError(""); setAck(""); }, [pump.pumpId]);
  function speak(text: string) {
    if (!("speechSynthesis" in window)) return;
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = lang;
    const voices = speechSynthesis.getVoices();
    const voice = voices.find((v) => v.localService && v.lang.startsWith(lang));
    if (voice) utterance.voice = voice;
    speechSynthesis.cancel(); speechSynthesis.speak(utterance);
  }
  useEffect(() => {
    if (!enabled || !alarm || alarmKey === ack) return;
    function cue() {
      if (prefs.vibrate) navigator.vibrate?.([250, 100, 250]);
      if (prefs.speak) speak(t("alert_spoken", { alarm: t(`alarm_${alarm}`), cause: t(`cause_${alarm}`) }));
      if (prefs.sound && audio.current) {
        const oscillator = audio.current.createOscillator(); const gain = audio.current.createGain();
        gain.gain.value = .08; oscillator.frequency.value = 520;
        oscillator.connect(gain); gain.connect(audio.current.destination); oscillator.start(); oscillator.stop(audio.current.currentTime + .3);
      }
    }
    cue(); const timer = setInterval(cue, 30000); return () => clearInterval(timer);
    // Notification settings and language intentionally re-cue the current alarm.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, alarmKey, ack, prefs, lang]);
  async function answer(action: "confirm" | "decline") {
    if (!proposal || busy) return;
    const version = proposal.version;
    setBusy(true); setError("");
    try { await api[action](pump.pumpId, version, caregiver); setAnswered(version); }
    catch (err) { setError(t(`error_${(err as { code?: string }).code || "generic"}`)); }
    finally { setBusy(false); }
  }
  function enable() {
    try { audio.current ||= new AudioContext(); audio.current.resume(); } catch { /* visual and speech remain */ }
    setEnabled(true);
  }
  return <div className="grid items-start gap-8 xl:grid-cols-[minmax(0,1.35fr)_minmax(340px,1fr)] xl:gap-12">
    <section aria-labelledby="feed-title" className="min-w-0">
      <div className="flex items-center justify-between gap-4 border-y border-line py-5"><h2 id="feed-title" className="text-lg font-semibold">{t("feed_session")}</h2><p className="flex items-center gap-2 text-sm font-medium" aria-live="polite">{s?.state === "running" && <span className="live-dot" />}{s ? t(`state_${s.state}`) : t("unknown")}</p></div>
      <div className="py-6 md:py-10"><FeedGauge delivered={delivered} target={target} /></div>
      <p className="text-center text-2xl font-medium tracking-tight tabular-nums">{target > 0 ? t("family_of_target", { delivered: `${number(delivered)} mL`, target: `${number(target)} mL` }) : t("family_no_feed")}</p>
      <dl className="mt-9 grid grid-cols-2 gap-6 border-t border-line pt-7 sm:grid-cols-3">
        {[{ label: t("family_rate_now"), value: s ? `${number(s.rate_ml_hr)} mL/hr` : "—" }, { label: t("remaining"), value: s ? `${number(Math.max(0, target - delivered))} mL` : "—" }, { label: t("clin_active_version"), value: s ? `v${s.prescription_version}` : "—" }].map((item) => <div key={item.label}><dt className="text-sm text-muted">{item.label}</dt><dd className="mt-2 text-xl font-semibold tracking-tight tabular-nums">{item.value}</dd></div>)}
      </dl>
      <button className="button mt-8" onClick={() => speak(t("family_status_spoken", { state: s ? t(`state_${s.state}`) : t("unknown"), delivered: `${number(delivered)} mL`, target: `${number(target)} mL` }))}><Volume2 size={17} aria-hidden="true" />{t("read")}</button>
    </section>
    <div className="min-w-0">
      {alarm && <section className="mb-6 rounded-2xl border-2 border-danger bg-panel p-6" role="alert"><h2 className="flex items-center gap-2 text-xl font-semibold text-danger"><CircleAlert size={22} aria-hidden="true" />{t(`alarm_${alarm}`)}</h2><p className="mt-3">{t(`cause_${alarm}`)}</p><ol className="mt-4 list-decimal space-y-3 pl-5">{list(`steps_${alarm}`).map((step) => <li key={step}>{step}</li>)}</ol><p className="mt-5 text-sm text-muted">{t("alert_ack_hint")}</p>{ack === alarmKey ? <p className="mt-4 font-medium">{t("alert_waiting")}</p> : <button className="button mt-4 w-full" onClick={() => setAck(alarmKey)}>{t("alert_done")}</button>}</section>}
      <Accordion icon={<FileCheck size={22} />} title={proposal ? t("review_title") : t("nothing_waiting")} subtitle={proposal ? t("review_version", { version: proposal.version }) : t("review_hint")} defaultOpen>
        <div ref={outcome} tabIndex={-1}>
        {proposal && proposal.version !== answered ? <div>
          <p className="mb-5 text-base text-muted">{t("review_intro", { clinician: user("clin-01") })}</p>
          <div className="grid grid-cols-[1fr_1fr_1fr] gap-3 border-b border-line pb-2 text-xs text-muted"><span /><span>{t("review_now")}</span><span>{t("review_new")}</span></div>
          {[{ name: t("field_rate"), before: active?.rate_ml_hr, after: proposal.rate_ml_hr, unit: "mL/hr" }, { name: t("field_volume"), before: active?.volume_ml, after: proposal.volume_ml, unit: "mL" }, { name: t("field_mode"), before: active?.mode ? t(`mode_${active.mode}`) : "—", after: t(`mode_${proposal.mode}`), unit: "" }].map((row) => <div key={row.name} className="grid grid-cols-3 gap-3 border-b border-line py-3 text-sm"><span className="text-muted">{row.name}</span><span>{row.before ?? "—"} {row.unit}</span><strong>{row.after} {row.unit}</strong></div>)}
          {proposal.note && <p className="mt-4 border-l-2 border-accent pl-4 text-base">{proposal.note}</p>}
          <p className="mt-5 text-sm" id="review-caregiver">{t("review_confirming_as", { who: user(caregiver) })}</p><p className="mt-2 text-sm text-muted">{t("review_queued_hint")}</p>
          <div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2"><button className="button" aria-describedby="review-caregiver" disabled={busy} onClick={() => answer("confirm")}>{t("review_confirm")}</button><button className="button" disabled={busy} onClick={() => answer("decline")}>{t("review_decline")}</button></div>
        </div> : latest ? <div role="status"><RxChip rx={latest} /><p className="mt-3 text-base">{latest.state === "active" ? t("review_active", { version: latest.version }) : latest.state === "rejected" ? (latest.reject_reason === "declined" ? t("review_declined") : t("review_rejected", { reason: t(`reason_${latest.reject_reason}`) })) : t(`rx_${latest.state}_detail`)}</p></div> : <div className="flex items-center gap-3 text-muted"><Check size={18} aria-hidden="true" /><p className="text-base">{t("review_none")}</p></div>}
        {error && <p role="alert" className="mt-3 text-base text-danger">{error}</p>}
        </div>
      </Accordion>
      <Accordion title={t("alerts_enable_title")} subtitle={enabled ? t("alerts_enabled") : t("alert_hint")} icon={<Bell size={22} />} defaultOpen>
        <p className="text-base text-muted">{t("alerts_enable_body")}</p><button className="button button-primary mt-4 w-full" disabled={enabled} onClick={enable}>{enabled ? t("alerts_enabled") : t("enable")}<ChevronRight size={16} aria-hidden="true" /></button>
      </Accordion>
      <Accordion title={t("settings_title")} subtitle={t("settings_hint")} icon={<Settings2 size={22} />}>
        <label htmlFor="caregiver" className="mb-2 block text-sm font-medium">{t("family_caregiver")}</label><select id="caregiver" className="input" value={caregiver} onChange={(event) => { setCaregiver(event.target.value); try { localStorage.setItem("sp-caregiver", event.target.value); } catch { /* session only */ } }}><option value="care-01">{t("role_parent")}</option><option value="care-02">{t("role_school_nurse")}</option></select>
        <fieldset className="mt-5"><legend className="mb-3 text-sm font-medium">{t("prefs_title", { who: user(caregiver) })}</legend>{(["vibrate", "sound", "speak"] as const).map((key) => <label key={key} className="flex min-h-12 items-center gap-3 text-base"><input type="checkbox" checked={prefs[key]} onChange={(event) => { const value = { ...prefs, [key]: event.target.checked }; setPrefs(value); try { localStorage.setItem(`sp-prefs-${caregiver}`, JSON.stringify(value)); } catch { /* session only */ } }} className="h-5 w-5 accent-accent" />{t(`pref_${key}`)}</label>)}</fieldset>
      </Accordion>
    </div>
  </div>;
}
