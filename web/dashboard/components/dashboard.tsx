"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { MotionConfig } from "framer-motion";
import { Activity, ArrowUpRight, Droplets, House, Moon, Sun, Users, Wifi, WifiOff } from "lucide-react";
import { useLocale } from "@/lib/locale";
import { usePump } from "@/lib/pump";
import { SimLabel } from "./primitives";
import { FamilyView } from "./family";
import { ClinicianView } from "./clinician";

export function Dashboard({ view }: { view: "family" | "clinician" }) {
  const { t, lang, setLang, date } = useLocale();
  const [pumpId, setPumpId] = useState("pump-001");
  const [night, setNight] = useState(false);
  const pump = usePump(pumpId);
  useEffect(() => {
    const id = new URLSearchParams(location.search).get("pump");
    if (id && /^[\w-]{1,64}$/.test(id)) setPumpId(id);
    setNight(document.documentElement.dataset.theme === "night");
  }, []);
  function theme() {
    const value = !night;
    setNight(value); document.documentElement.dataset.theme = value ? "night" : "day";
    try { localStorage.setItem("sp-theme", value ? "night" : "day"); } catch { /* session only */ }
  }
  function selectPump(id: string) {
    setPumpId(id); history.replaceState(null, "", `?pump=${encodeURIComponent(id)}`);
  }
  const status = pump.stream === "connecting" ? t("connecting") : pump.online ? t("connected") : t("disconnected");
  return <MotionConfig reducedMotion="user">
    <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-panel focus:p-4">{t("skip_to_content")}</a>
    <div className="grid min-h-screen grid-cols-1 lg:grid-cols-[88px_minmax(0,1fr)]">
      <aside className="flex items-center justify-between border-b border-line px-4 py-3 lg:flex-col lg:justify-start lg:border-r lg:border-b-0 lg:px-3 lg:py-7">
        <Link href="/" aria-label={t("brand_name")} className="control grid h-12 w-12 place-items-center rounded-2xl bg-accent text-panel"><Droplets size={25} aria-hidden="true" /></Link>
        <nav aria-label={t("page_sections")} className="flex gap-2 lg:mt-12 lg:flex-col lg:gap-5">
          {[{ href: "/", key: "family", Icon: House }, { href: "/clinician", key: "clinician", Icon: Users }].map(({ href, key, Icon }) => <Link key={key} href={`${href}?pump=${pumpId}`} aria-current={view === key ? "page" : undefined} className={`control flex flex-col items-center justify-center gap-1 rounded-xl px-3 py-2 text-[11px] ${view === key ? "bg-tint text-accent" : "text-muted hover:bg-tint"}`}><Icon size={21} aria-hidden="true" /><span>{t(key)}</span></Link>)}
        </nav>
        <Activity size={20} className="mt-auto hidden text-muted lg:block" aria-hidden="true" />
      </aside>
      <div className="min-w-0">
        <header className="flex flex-wrap items-center justify-between gap-4 border-b border-line px-5 py-5 md:px-10">
          <div><p className="kicker">{t("brand_name")}</p><p className="mt-1 text-sm font-medium">{t("workspace")}</p></div>
          <div className="flex flex-wrap items-center gap-3">
            {pump.status?.simulated !== false && <SimLabel />}
            <label className="sr-only" htmlFor="language">{t("language_label")}</label><select id="language" value={lang} onChange={(event) => setLang(event.target.value as "en" | "es")} className="rounded-lg border border-line bg-panel px-3 text-sm"><option value="en">English</option><option value="es">Español</option></select>
            <button className="button" aria-pressed={night} onClick={theme}>{night ? <Sun size={17} aria-hidden="true" /> : <Moon size={17} aria-hidden="true" />}{t(night ? "light" : "dark")}</button>
          </div>
        </header>
        <main id="main" tabIndex={-1} className="mx-auto max-w-[1500px] px-5 py-8 md:px-10 md:py-10">
          <div className="mb-9 flex flex-wrap items-end justify-between gap-5">
            <div><p className="kicker mb-3">{t(view === "family" ? "family_space" : "clinical_space")} / {t("overview")}</p><h1 className="font-display text-4xl tracking-[-.045em] md:text-5xl">{t(view === "family" ? "feed_overview" : "care_overview")}</h1><p className="mt-3 text-base text-muted">{t(view === "family" ? "family_dashboard_intro" : "clinical_dashboard_intro")}</p></div>
            <div className="text-sm text-muted"><p className="flex items-center gap-2" role="status">{pump.online ? <Wifi size={16} aria-hidden="true" /> : <WifiOff size={16} aria-hidden="true" />}{status}</p><p className="mt-1 text-xs">{date(pump.lastUpdateAt)}</p></div>
          </div>
          {!pump.online && pump.stream !== "connecting" && <div className="mb-6 rounded-xl border border-warm p-4 text-warm" role="status"><strong>{t("disconnected")}</strong><p className="mt-1 text-base">{t("data_stale")} {t(pump.stream === "lost" ? "hub_lost" : "pump_offline_body")}</p></div>}
          {view === "family" ? <FamilyView pump={pump} /> : <ClinicianView pump={pump} selectPump={selectPump} />}
        </main>
        <footer className="flex flex-wrap justify-between gap-3 border-t border-line px-5 py-5 text-xs text-muted md:px-10"><p><strong>{t("prototype_footer")}</strong> {t("prototype_footer_detail")}</p><span className="inline-flex items-center gap-1">{t("brand_name")} <ArrowUpRight size={12} aria-hidden="true" /></span></footer>
      </div>
    </div>
  </MotionConfig>;
}
