"use client";
import { useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { BedDouble, ChevronLeft, ChevronRight, Cross, Layers, Radio } from "lucide-react";
import { useLocale } from "@/lib/locale";
import type { Patient, Pump } from "@/lib/pump";
import { motionTokens } from "@/lib/motion";
import { TelemetryOverlay } from "./telemetry";

// A schematic, not inferred locations. Paginated slots also support larger rosters.
const slots = [{ x: 21, y: 28 }, { x: 50, y: 28 }, { x: 79, y: 28 }, { x: 21, y: 73 }, { x: 50, y: 73 }, { x: 79, y: 73 }];
export function WardMap({ patients, selected, choose, pump, demoVitals, setDemoVitals }: {
  patients: Patient[]; selected: string; choose: (id: string) => void; pump: Pump;
  demoVitals: boolean; setDemoVitals: (value: boolean) => void;
}) {
  const { t } = useLocale();
  const reduced = useReducedMotion();
  const [page, setPage] = useState(0);
  const pages = Math.max(1, Math.ceil(patients.length / 6));
  const current = Math.min(page, pages - 1);
  const beds = patients.slice(current * 6, current * 6 + 6);
  const patient = patients.find((p) => p.pump_id === selected);
  return <div className="ward-stage relative min-h-0 flex-1 overflow-hidden">
    <div className="map-tools absolute top-4 right-5 left-5 z-10 flex items-center justify-between gap-2 text-[10px] text-muted"><span className="flex items-center gap-2"><Layers size={13} aria-hidden="true" />{t("demo_layout")}</span><span className="flex items-center gap-2"><span className="status-dot bg-accent" />{t("live_feed")}</span></div>
    <div className="floor-plan absolute">
      <svg className="absolute inset-0 h-full w-full" viewBox="0 0 1000 650" preserveAspectRatio="none" role="img" aria-label={t("ward_subtitle")}>
        <defs><pattern id="map-grid" width="30" height="30" patternUnits="userSpaceOnUse"><path d="M30 0H0V30" fill="none" stroke="#153039" strokeWidth=".7" /></pattern></defs>
        <rect width="1000" height="650" fill="url(#map-grid)" />
        <path d="M55 65H945V585H55Z" fill="#0c1d25" stroke="#36515c" strokeWidth="3" />
        <path d="M55 280H945V370H55Z" fill="#112730" stroke="#36515c" strokeWidth="2" />
        {[345, 655].map((x) => <path key={x} d={`M${x} 65V280M${x} 370V585`} stroke="#36515c" strokeWidth="3" />)}
        {[195, 495, 795].map((x) => <g key={x} stroke="#547581" strokeWidth="2" fill="none"><path d={`M${x} 280h65M${x} 370h65`} stroke="#0c1d25" strokeWidth="5" /><path d={`M${x} 280v-55a55 55 0 0 1 55 55M${x} 370v55a55 55 0 0 0 55-55`} strokeDasharray="3 4" /></g>)}
        <path d="M55 325H370M630 325H945" stroke="#24434d" strokeWidth="2" strokeDasharray="7 7" />
      </svg>
      <div className="station-label absolute top-[46%] left-1/2 flex -translate-x-1/2 items-center gap-2 whitespace-nowrap rounded-md border border-line bg-panel px-3 py-2 text-[10px] text-muted"><Cross size={13} className="text-accent" aria-hidden="true" />{t("station")}</div>
      <AnimatePresence mode="wait" initial={false}>
        <motion.div key={current} className="absolute inset-0" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: motionTokens.duration.fast }}>
          {beds.map((bed, index) => {
            const active = selected === bed.pump_id;
            return <motion.button key={bed.id} className={`bed-marker absolute flex -translate-x-1/2 -translate-y-1/2 flex-col items-center rounded-xl ${active ? "text-accent" : "text-muted"}`} style={{ left: `${slots[index].x}%`, top: `${slots[index].y}%` }} aria-label={`${t("bed")} ${current * 6 + index + 1}: ${bed.display_name}`} aria-pressed={active} onClick={() => choose(bed.pump_id)} whileTap={reduced ? undefined : { scale: motionTokens.scale.press }}>
              {active && <motion.span layoutId={reduced ? undefined : "selected-bed"} className="absolute inset-0 rounded-xl border border-accent bg-tint/70 shadow-[0_0_40px_#20dbc318]" />}
              <span className="relative mb-1 flex items-center gap-2 text-[9px] tracking-[.12em] uppercase"><span className={`status-dot ${bed.exceptions.length ? "bg-warm" : bed.online ? "bg-accent" : "bg-muted"}`} />{t("bed")} {String(current * 6 + index + 1).padStart(2, "0")}</span>
              <BedDouble className="relative my-1" size={40} strokeWidth={1.1} aria-hidden="true" />
              <span className="relative max-w-full truncate text-[10px] font-medium text-ink">{bed.display_name.replace(/^Demo Child /, "")}</span>
              <span className="relative mt-1 text-[8px] text-muted">{bed.pump_id}</span>
            </motion.button>;
          })}
        </motion.div>
      </AnimatePresence>
    </div>
    {!patients.length && <p className="absolute top-1/2 right-5 left-5 text-center text-sm text-muted">{t("select_patient")}</p>}
    <TelemetryOverlay key={selected} patient={patient} pump={pump} enabled={demoVitals} />
    <div className="map-footer absolute right-5 bottom-3 left-5 flex items-center justify-between gap-2 border-t border-line pt-3">
      <button className="flex items-center gap-2 text-[10px] text-muted" aria-pressed={demoVitals} onClick={() => setDemoVitals(!demoVitals)}><Radio size={13} className={demoVitals ? "text-accent" : "text-muted"} aria-hidden="true" />{t("demo_vitals")}<span className={`h-1.5 w-1.5 rounded-full ${demoVitals ? "bg-accent" : "bg-muted"}`} /></button>
      <div className="flex items-center gap-2"><button className="small-icon" aria-label={t("previous")} disabled={current === 0} onClick={() => setPage(current - 1)}><ChevronLeft size={13} /></button><span className="text-[10px] text-muted">{current + 1} / {pages}</span><button className="small-icon" aria-label={t("next")} disabled={current + 1 === pages} onClick={() => setPage(current + 1)}><ChevronRight size={13} /></button></div>
    </div>
  </div>;
}
