"use client";
import Link from "next/link";
import { FamilyHome } from "./family-home";
import { useEffect, useRef, useState } from "react";
import { AnimatePresence, LayoutGroup, MotionConfig, motion, useReducedMotion } from "framer-motion";
import { Activity, Bell, ChevronLeft, ChevronRight, Globe2, Map, Moon, Sun, PanelRightOpen, Search, Users, Wifi, WifiOff } from "lucide-react";
import { useLocale } from "@/lib/locale";
import { usePump, useResource, type Patient } from "@/lib/pump";
import { motionTokens, springs } from "@/lib/motion";
import { WardMap } from "./ward-map";
import { PatientDetailsPane } from "./patient-details";

type Section = "global" | "ward_map" | "patients_nav" | "alerts_nav";
export function Dashboard({ view }: { view: "family" | "clinician" }) {
  const { t, lang, setLang } = useLocale();
  const reduced = useReducedMotion();
  const [section, setSection] = useState<Section>("global");
  const [pumpId, setPumpId] = useState("pump-001");
  const [open, setOpen] = useState(false);
  const [mapReset, setMapReset] = useState(0);
  const [panelWidth, setPanelWidth] = useState(380);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const [demoVitals, setDemoVitals] = useState(true);
  const [light, setLight] = useState(false);
  const pump = usePump(pumpId);
  const roster = useResource<Patient[]>("/api/patients", 5000);
  const patients = roster.data || [];
  const selected = patients.find((patient) => patient.pump_id === pumpId);
  const main = useRef<HTMLElement>(null);
  useEffect(() => {
    setLight(document.documentElement.dataset.theme === "day");
    const id = new URLSearchParams(location.search).get("pump");
    if (id && /^[\w-]{1,64}$/.test(id)) setPumpId(id);
    if (window.matchMedia("(max-width: 900px)").matches) setOpen(false);
    const compact = window.matchMedia("(max-width: 900px)");
    const medium = window.matchMedia("(max-width: 1100px)");
    const size = () => setPanelWidth(compact.matches ? 0 : medium.matches ? 340 : 380);
    size(); compact.addEventListener("change", size); medium.addEventListener("change", size);
    return () => { compact.removeEventListener("change", size); medium.removeEventListener("change", size); };
  }, []);
  useEffect(() => { setSection("global"); setOpen(false); }, [view]);
  function toggleTheme() {
    const next = !light; setLight(next);
    document.documentElement.dataset.theme = next ? "day" : "night";
    try { localStorage.setItem("sp-theme", next ? "day" : "night"); } catch { /* session-only setting */ }
  }
  function choose(id: string) {
    setPumpId(id); setOpen(true);
    history.replaceState(null, "", `?pump=${encodeURIComponent(id)}`);
    requestAnimationFrame(() => main.current?.querySelector<HTMLElement>("[data-patient-heading]")?.focus({ preventScroll: true }));
  }
  function navigate(value: Section) { setSection(value); setPage(0); setSearch(""); if (window.matchMedia("(max-width: 900px)").matches) setOpen(false); }
  function close() { setOpen(false); if (view === "clinician") setMapReset((value) => value + 1); requestAnimationFrame(() => main.current?.focus()); }
  const filtered = patients.filter((patient) => {
    const flagged = patient.exceptions.length > 0 || (patient.pump_id === pumpId && pump.alerts.some((a) => a.active));
    return (section !== "alerts_nav" || flagged) && `${patient.display_name} ${patient.pump_id}`.toLowerCase().includes(search.toLowerCase());
  });
  const total = Math.max(1, Math.ceil(filtered.length / 6));
  const currentPage = Math.min(page, total - 1);
  const visible = filtered.slice(currentPage * 6, currentPage * 6 + 6);
  const connected = patients.filter((p) => p.online).length;
  const flagged = patients.filter((p) => p.exceptions.length || (p.pump_id === pumpId && pump.alerts.some((a) => a.active))).length;
  const status = pump.stream === "connecting" ? t("connecting") : t(pump.online ? "connected" : "disconnected");
  const family = view === "family";
  const mapView = section === "global" || section === "ward_map";
  return <MotionConfig reducedMotion="user" transition={springs.snappy}><LayoutGroup id="care-command">
    <a href="#main" className="skip-link">{t("skip_to_content")}</a>
    <div className="command-shell grid h-screen w-screen grid-cols-[72px_minmax(0,1fr)] overflow-hidden">
      <aside className="nav-rail flex min-h-0 flex-col items-center border-r border-line py-5">
        <div className="brand-mark grid h-11 w-11 shrink-0 place-items-center rounded-xl text-accent" aria-label={t("brand_name")}><Activity size={25} aria-hidden="true" /></div>
        <nav aria-label={t("page_sections")} className="mt-8 flex w-full flex-col gap-3 px-2">
          {(family ? [{ id: "global", Icon: Globe2 }] as const : [{ id: "global", Icon: Globe2 }, { id: "ward_map", Icon: Map }, { id: "patients_nav", Icon: Users }, { id: "alerts_nav", Icon: Bell }] as const).map(({ id, Icon }) => <button key={id} onClick={() => navigate(id)} aria-current={section === id ? "page" : undefined} className={`rail-button relative flex flex-col items-center gap-2 rounded-xl px-1 py-3 ${section === id ? "text-accent" : "text-muted"}`}>
            {section === id && <motion.span layoutId={reduced ? undefined : "navigation-active"} className="absolute inset-0 rounded-xl bg-tint" />}
            <Icon size={21} strokeWidth={1.6} className="relative" aria-hidden="true" /><span className="relative text-[10px] font-medium">{t(id)}</span>
          </button>)}
        </nav>
        <span className="mt-auto pt-3 text-[10px] text-muted">SP / 01</span>
      </aside>
      <div className="grid min-h-0 min-w-0 shell-content grid-rows-[100px_minmax(0,1fr)_26px]">
        <header className="shell-header relative flex min-w-0 items-center justify-between gap-3 border-b border-line px-5">
          <div className="min-w-0"><p className="text-sm font-semibold tracking-wide">{t("brand_name")}<span className="hidden text-muted sm:inline"> / {t("command_center")}</span></p><p className="mt-1 text-[10px] tracking-[.15em] text-muted uppercase">{t(family ? "family_home_title" : "clinician_home_title")}</p></div>
          <div className="header-controls flex shrink-0 items-center gap-4"><button className="icon-button" aria-label={t(light ? "switch_dark" : "switch_light")} aria-pressed={light} onClick={toggleTheme}>{light ? <Moon size={15} aria-hidden="true" /> : <Sun size={15} aria-hidden="true" />}</button><p className={`connection flex items-center gap-2 text-xs ${pump.online ? "text-accent" : "text-warm"}`} role="status">{pump.online ? <Wifi size={14} aria-hidden="true" /> : <WifiOff size={14} aria-hidden="true" />}<span className="hidden sm:inline">{status}</span></p>
            <label htmlFor="language" className="sr-only">{t("language_label")}</label><select id="language" className="language-select rounded-md border border-line bg-panel px-2 text-xs" value={lang} onChange={(e) => setLang(e.target.value as "en" | "es")}><option value="en">EN</option><option value="es">ES</option></select>
          </div>
          <nav className="demo-role-switch" aria-label={t("demo_view")}><span>{t("demo_view")}</span>{(["family", "clinician"] as const).map((role) => <Link key={role} href={`${role === "family" ? "/" : "/clinician"}?pump=${encodeURIComponent(pumpId)}`} aria-current={view === role ? "page" : undefined} className={view === role ? "active" : ""}>{view === role && <motion.span layoutId="demo-role" className="role-highlight" />}<span className="relative">{t(role)}</span></Link>)}</nav>
        </header>
        <motion.main id="main" tabIndex={-1} ref={main} className="split-grid relative grid min-h-0 min-w-0 overflow-hidden" data-open={open} animate={{ gridTemplateColumns: panelWidth ? `minmax(0, 1fr) ${open ? panelWidth : 0}px` : "minmax(0, 1fr)" }} transition={{ duration: reduced ? 0 : motionTokens.duration.normal, ease: motionTokens.easing.smooth }} onKeyDown={(event) => { if (event.key === "Escape" && open) close(); }}>
          <section className="visual-pane flex min-h-0 min-w-0 flex-col overflow-hidden" aria-label={t(section)}>
            <div className="pane-heading flex shrink-0 items-center justify-between gap-3 px-6 pt-5 pb-4"><div className="min-w-0"><p className="kicker mb-1">{t(family ? "family" : "clinician")} / {t("home_care")}</p><h1 className="text-xl font-semibold tracking-tight">{t(family ? "family_home_title" : mapView ? "ward" : section === "patients_nav" ? "all_patients" : "review_flags")}</h1></div>{!open && <button className="icon-button" onClick={() => setOpen(true)} aria-label={t("open_details")}><PanelRightOpen size={20} /></button>}</div>
            {!family && <div className="ward-metrics grid shrink-0 grid-cols-3 border-y border-line">
              {[{ label: "monitored", value: patients.length, suffix: "" }, { label: "connected_pumps", value: connected, suffix: ` / ${patients.length}` }, { label: "needs_review", value: flagged, suffix: "" }].map(({ label, value, suffix }) => <div key={label} className="px-6 py-3"><p className="text-[10px] text-muted">{t(label)}</p><p className={`mt-1 text-2xl font-medium tabular-nums ${label === "needs_review" && value ? "text-warm" : "text-ink"}`}>{roster.data ? value : "—"}<span className="text-xs text-muted">{suffix}</span></p></div>)}
            </div>}
            <AnimatePresence mode="wait" initial={false}>
              <motion.div key={mapView ? "map" : section} className="relative flex min-h-0 flex-1 flex-col overflow-hidden" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: motionTokens.duration.fast }}>
                {family ? <FamilyHome pump={pump} patient={selected} patients={patients} choose={(id) => { setPumpId(id); history.replaceState(null, "", `?pump=${encodeURIComponent(id)}`); }} inspect={() => setOpen(true)} /> : mapView ? <WardMap resetSignal={mapReset} patients={patients} selected={pumpId} choose={choose} pump={pump} demoVitals={demoVitals} setDemoVitals={setDemoVitals} /> : <>
                  <div className="px-6 py-4"><label className="relative block"><Search size={16} className="absolute top-3.5 left-3 text-muted" aria-hidden="true" /><span className="sr-only">{t("patient_search")}</span><input value={search} onChange={(e) => { setSearch(e.target.value); setPage(0); }} className="input pl-10! text-sm!" placeholder={t("patient_search")} /></label></div>
                  <div className="local-scroll min-h-0 flex-1 overflow-y-auto px-6" aria-label={t(section)} tabIndex={0}>
                    {roster.error && <p role="status" className="py-4 text-sm text-warm">{t("roster_unavailable")}</p>}
                    {!roster.data ? <p className="py-4 text-muted">{t("loading")}</p> : !visible.length ? <p className="py-8 text-muted">{t(section === "alerts_nav" && !search ? "no_attention" : "no_matches")}</p> : visible.map((patient) => <motion.button key={patient.id} onClick={() => choose(patient.pump_id)} aria-pressed={patient.pump_id === pumpId && open} className={`patient-row flex w-full items-center justify-between gap-4 border-b border-line py-5 text-left ${patient.pump_id === pumpId ? "text-accent" : "text-ink"}`} whileTap={reduced ? undefined : { scale: motionTokens.scale.press }}>
                      <span className="min-w-0"><span className="block text-sm font-semibold">{patient.display_name}</span><span className="mt-1 block text-xs text-muted">{patient.pump_id}</span><span className="mt-2 block text-xs text-warm">{patient.exceptions.map((code) => t(`exc_${code}`)).join(" · ") || t("exc_none")}</span></span><ChevronRight size={18} className="shrink-0" aria-hidden="true" />
                    </motion.button>)}
                  </div>
                  <div className="flex shrink-0 items-center justify-between gap-3 border-t border-line px-6 py-3"><button className="icon-button" aria-label={t("previous")} disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}><ChevronLeft size={17} /></button><span className="text-xs text-muted">{t("page_count", { page: currentPage + 1, total })}</span><button className="icon-button" aria-label={t("next")} disabled={currentPage + 1 === total} onClick={() => setPage(currentPage + 1)}><ChevronRight size={17} /></button></div>
                </>}
              </motion.div>
            </AnimatePresence>
            {mapView && roster.error && <p role="status" className="shrink-0 px-6 py-2 text-xs text-warm">{t("roster_unavailable")}</p>}
          </section>
          <PatientDetailsPane key={`${view}-${pumpId}`} role={view} active={open} pump={pump} patient={selected} defaultTab={view === "clinician" ? "orders" : "care"} close={close} selectPump={choose} telemetryEnabled={demoVitals} />
        </motion.main>
        <footer className="flex items-center justify-between gap-2 border-t border-line px-4 text-[9px] text-muted"><p className="truncate">{t("prototype_footer")} · {t("simulated_data")}</p><span className="shrink-0 font-mono">SMART PUMP / WEB</span></footer>
      </div>
    </div>
  </LayoutGroup></MotionConfig>;
}
