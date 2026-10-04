"use client";
import { useEffect, useId, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { BedDouble, ChevronLeft, ChevronRight, Cross, Layers, Minus, Plus, Radio, Scan } from "lucide-react";
import { useLocale } from "@/lib/locale";
import type { Patient, Pump } from "@/lib/pump";
import { motionTokens } from "@/lib/motion";
import { useMapCamera } from "@/lib/use-map-camera";
import { MIN_ZOOM, MAX_ZOOM } from "@/lib/map-camera";

const slots = [{ x: .21, y: .28 }, { x: .5, y: .28 }, { x: .79, y: .28 }, { x: .21, y: .73 }, { x: .5, y: .73 }, { x: .79, y: .73 }];
export function WardMap({ patients, selected, choose, pump, demoVitals, setDemoVitals }: {
  patients: Patient[]; selected: string; choose: (id: string) => void; pump: Pump;
  demoVitals: boolean; setDemoVitals: (value: boolean) => void;
}) {
  const { t, number } = useLocale();
  const reduced = useReducedMotion();
  const camera = useMapCamera();
  const pattern = useId().replace(/:/g, "");
  const [page, setPage] = useState(0);
  const [hover, setHover] = useState<string | null>(null);
  const pages = Math.max(1, Math.ceil(patients.length / 6));
  const current = Math.min(page, pages - 1);
  const beds = patients.slice(current * 6, current * 6 + 6);
  const patient = patients.find((p) => p.pump_id === selected);
  const lastSelected = useRef(selected);
  const center = useRef(camera.center);
  center.current = camera.center;
  useEffect(() => {
    if (selected === lastSelected.current) return;
    lastSelected.current = selected;
    const index = beds.findIndex((bed) => bed.pump_id === selected);
    if (index >= 0) center.current(slots[index].x, slots[index].y);
  }, [selected, beds]);
  function turnPage(next: number) { setPage(next); setHover(null); camera.reset(); }
  return <div className="ward-stage relative min-h-0 flex-1 overflow-hidden">
    <div className="map-tools absolute top-4 right-5 left-5 z-10 flex items-center justify-between gap-2 text-[10px] text-muted"><span className="flex items-center gap-2"><Layers size={13} aria-hidden="true" />{t("demo_layout")}</span><span className="flex items-center gap-2"><span className={`status-dot ${pump.online ? "bg-accent" : "bg-warm"}`} />{t(pump.online ? "live_feed" : "disconnected")}</span></div>
    <div ref={camera.viewport} {...camera.events} className={`floor-plan map-viewport absolute overflow-hidden ${camera.dragging ? "is-dragging" : ""}`} role="region" aria-label={t("map_navigation")} tabIndex={0} onKeyDown={(event) => {
      if (event.target !== event.currentTarget) return;
      if (event.key === "+" || event.key === "=") { event.preventDefault(); camera.zoomBy(1.25); }
      if (event.key === "-") { event.preventDefault(); camera.zoomBy(.8); }
      if (event.key === "0") { event.preventDefault(); camera.reset(); }
    }}>
      <motion.div className="map-canvas absolute inset-0" style={{ x: camera.x, y: camera.y, scale: camera.scale, transformOrigin: "0 0" }}>
        <svg className="absolute inset-0 h-full w-full" viewBox="0 0 1000 650" preserveAspectRatio="none" aria-hidden="true">
          <defs><pattern id={pattern} width="30" height="30" patternUnits="userSpaceOnUse"><path d="M30 0H0V30" fill="none" stroke="var(--map-grid)" strokeWidth=".7" /></pattern></defs>
          <rect width="1000" height="650" fill={`url(#${pattern})`} />
          <path d="M55 65H945V585H55Z" fill="var(--map-room)" stroke="var(--map-wall)" strokeWidth="3" />
          <path d="M55 280H945V370H55Z" fill="var(--map-corridor)" stroke="var(--map-wall)" strokeWidth="2" />
          {[345, 655].map((x) => <path key={x} d={`M${x} 65V280M${x} 370V585`} stroke="var(--map-wall)" strokeWidth="3" />)}
          {[195, 495, 795].map((x) => <g key={x} stroke="var(--map-door)" strokeWidth="2" fill="none"><path d={`M${x} 280h65M${x} 370h65`} stroke="var(--map-room)" strokeWidth="5" /><path d={`M${x} 280v-55a55 55 0 0 1 55 55M${x} 370v55a55 55 0 0 0 55-55`} strokeDasharray="3 4" /></g>)}
          <path d="M55 325H370M630 325H945" stroke="var(--map-grid)" strokeWidth="2" strokeDasharray="7 7" />
        </svg>
        <div className="station-label pointer-events-none absolute top-[46%] left-1/2 flex -translate-x-1/2 items-center gap-2 whitespace-nowrap rounded-md border border-line bg-panel px-3 py-2 text-[10px] text-muted"><Cross size={13} className="text-accent" aria-hidden="true" />{t("station")}</div>
        <AnimatePresence mode="wait" initial={false}><motion.div key={current} className="absolute inset-0" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: motionTokens.duration.fast }}>
          {beds.map((bed, index) => {
            const active = selected === bed.pump_id;
            const critical = bed.pump_id === pump.pumpId && pump.alerts.some((alert) => alert.active);
            const attention = bed.exceptions.length > 0;
            const tag = bed.pump_id === pump.pumpId && pump.status?.received_at ? `${number(pump.status.rate_ml_hr)} mL/hr` : demoVitals && bed.simulated && pump.status?.simulated ? `${t("demo_short")} HR: ${72 + Array.from(bed.pump_id).reduce((sum, c) => sum + c.charCodeAt(0), 0) % 12}` : t(bed.online ? "connected" : "disconnected");
            return <div key={bed.id} className="bed-position absolute -translate-x-1/2 -translate-y-1/2" style={{ left: `${slots[index].x * 100}%`, top: `${slots[index].y * 100}%` }}>
              <motion.button className="bed-marker relative flex flex-col items-center rounded-xl" data-state={critical ? "critical" : active ? "selected" : attention ? "attention" : "idle"} aria-label={`${t("bed")} ${current * 6 + index + 1}: ${bed.display_name}${critical ? ` · ${t("active_alarm")}` : attention ? ` · ${t("needs_review")}` : ""}`} aria-pressed={active} onClick={() => { camera.center(slots[index].x, slots[index].y); choose(bed.pump_id); }} onHoverStart={() => setHover(bed.id)} onHoverEnd={() => setHover(null)} onFocus={(event) => { setHover(bed.id); if (event.currentTarget.matches(":focus-visible")) { camera.viewport.current?.scrollTo(0, 0); camera.center(slots[index].x, slots[index].y); } }} onBlur={() => setHover(null)} whileHover={reduced ? undefined : { scale: motionTokens.scale.hover }} whileTap={reduced ? undefined : { scale: motionTokens.scale.press }}>
                <AnimatePresence initial={false}>{(active || critical || attention) && <motion.span key={critical ? "critical" : active ? "selected" : "attention"} className="node-pulse pointer-events-none absolute top-1/2 left-1/2 h-20 w-20 rounded-full border" style={{ color: critical ? "var(--danger)" : active ? "var(--accent)" : "var(--warm)", marginLeft: -40, marginTop: -40 }} initial={{ opacity: 0 }} animate={reduced ? { opacity: .35 } : { scale: [1, 1.65], opacity: [.45, 0] }} exit={{ opacity: 0 }} transition={reduced ? { duration: 0 } : { duration: motionTokens.duration.pulse, repeat: Infinity, ease: "easeOut" }} />}</AnimatePresence>
                <span className="relative mb-1 flex items-center gap-2 text-[9px] tracking-[.12em] uppercase"><span className={`status-dot ${critical ? "bg-danger" : attention ? "bg-warm" : bed.online ? "bg-accent" : "bg-muted"}`} />{t("bed")} {String(current * 6 + index + 1).padStart(2, "0")}</span>
                <BedDouble className="relative my-1" size={40} strokeWidth={1.1} aria-hidden="true" />
                <span className="relative max-w-full truncate text-[10px] font-medium text-ink">{bed.display_name.replace(/^Demo Child /, "")}</span><span className="relative mt-1 text-[8px] text-muted">{bed.pump_id}</span>
              </motion.button>
              <AnimatePresence initial={false}>{(hover === bed.id || camera.zoom >= 1.8) && <motion.span key="telemetry" className="node-tag pointer-events-none absolute top-full left-1/2 z-20 mt-1 -translate-x-1/2 whitespace-nowrap rounded-md border border-line bg-panel px-2 py-1 text-[9px] text-ink" initial={{ opacity: 0, y: reduced ? 0 : -motionTokens.distance.sm }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: motionTokens.duration.fast }}>{tag}</motion.span>}</AnimatePresence>
            </div>;
          })}
        </motion.div></AnimatePresence>
      </motion.div>
    </div>
    <div className="map-camera-tools absolute z-20 flex items-center gap-1 rounded-lg border border-line bg-panel p-1" role="group" aria-label={t("map_navigation")}>
      <button className="small-icon" onClick={() => camera.zoomBy(.8)} disabled={camera.zoom <= MIN_ZOOM} aria-label={t("zoom_out")}><Minus size={14} /></button><output className="w-10 text-center text-[10px] text-muted" aria-label={t("map_zoom")}>{Math.round(camera.zoom * 100)}%</output><button className="small-icon" onClick={() => camera.zoomBy(1.25)} disabled={camera.zoom >= MAX_ZOOM} aria-label={t("zoom_in")}><Plus size={14} /></button><button className="small-icon" onClick={camera.reset} aria-label={t("reset_map")}><Scan size={14} /></button>
    </div>
    {!patients.length && <p className="pointer-events-none absolute top-1/2 right-5 left-5 text-center text-sm text-muted">{t("select_patient")}</p>}
    <div className="map-footer absolute right-5 bottom-3 left-5 flex items-center justify-between gap-2 border-t border-line pt-3"><button className="flex items-center gap-2 text-[10px] text-muted" aria-pressed={demoVitals} onClick={() => setDemoVitals(!demoVitals)}><Radio size={13} className={demoVitals ? "text-accent" : "text-muted"} aria-hidden="true" />{t("demo_vitals")}<span className={`h-1.5 w-1.5 rounded-full ${demoVitals ? "bg-accent" : "bg-muted"}`} /></button><div className="flex items-center gap-2"><button className="small-icon" aria-label={t("previous")} disabled={current === 0} onClick={() => turnPage(current - 1)}><ChevronLeft size={13} /></button><span className="text-[10px] text-muted">{current + 1} / {pages}</span><button className="small-icon" aria-label={t("next")} disabled={current + 1 === pages} onClick={() => turnPage(current + 1)}><ChevronRight size={13} /></button></div></div>
  </div>;
}
