"use client";
import { useEffect, useState } from "react";
import { AnimatePresence, animate, motion, useMotionValue, useReducedMotion, useTransform } from "framer-motion";
import { Heart, Wind } from "lucide-react";
import { PolarAngleAxis, RadialBar, RadialBarChart } from "recharts";
import { motionTokens } from "@/lib/motion";
import { useLocale } from "@/lib/locale";
import type { Patient, Pump } from "@/lib/pump";

function Dial({ value, max, label, unit, oxygen = false }: { value: number; max: number; label: string; unit: string; oxygen?: boolean }) {
  const reduced = useReducedMotion();
  const animated = useMotionValue(value);
  const display = useTransform(animated, (number) => Math.round(number));
  useEffect(() => { const controls = animate(animated, value, { duration: reduced ? 0 : motionTokens.duration.telemetry }); return () => controls.stop(); }, [value, animated, reduced]);
  return <div className="vital-widget flex items-center gap-2 rounded-xl border border-line bg-panel/95 p-3 shadow-xl" role="img" aria-label={`${label}: ${value} ${unit}. Simulated.`}>
    <div className="relative h-[78px] w-[78px] shrink-0" aria-hidden="true"><RadialBarChart width={78} height={78} data={[{ value, fill: "var(--accent)" }]} innerRadius="81%" outerRadius="100%" startAngle={90} endAngle={-270}><PolarAngleAxis type="number" domain={[0, max]} tick={false} /><RadialBar dataKey="value" background={{ fill: "var(--track)" }} cornerRadius={8} isAnimationActive={!reduced} animationDuration={motionTokens.duration.telemetry * 1000} /></RadialBarChart><div className="absolute inset-0 flex flex-col items-center justify-center"><motion.span className="text-xl font-medium tabular-nums">{display}</motion.span><span className="text-[8px] text-muted">{unit}</span></div></div>
    <div className="min-w-0"><div className="mb-2 text-accent">{oxygen ? <Wind size={16} aria-hidden="true" /> : <Heart size={16} aria-hidden="true" />}</div><p className="text-[11px] font-medium">{label}</p><svg className="mt-2 h-4 w-20 text-accent" viewBox="0 0 100 20" aria-hidden="true"><path d={oxygen ? "M0 14Q10 0 20 14T40 14T60 14T80 14T100 14" : "M0 12H20L25 8L30 16L36 1L43 19L49 12H62L68 7L73 12H100"} fill="none" stroke="currentColor" strokeWidth="1.5" /></svg></div>
  </div>;
}
export function TelemetryOverlay({ patient, pump, enabled }: { patient?: Patient; pump: Pump; enabled: boolean }) {
  const { t } = useLocale();
  const reduced = useReducedMotion();
  const [tick, setTick] = useState(0);
  // The actual pump protocol contains no HR/SpO2. Never synthesize them for a real source.
  const simulated = pump.status?.simulated === true && patient?.simulated === true;
  const show = enabled && simulated;
  useEffect(() => {
    if (!show) return;
    const interval = setInterval(() => setTick((value) => value + 1), 2500);
    return () => clearInterval(interval);
  }, [show]);
  const seed = Array.from(pump.pumpId).reduce((sum, c) => sum + c.charCodeAt(0), 0);
  const heart = 72 + seed % 12 + Math.round(Math.sin(tick * .7) * 4);
  const oxygen = 97 + Math.round((Math.sin(tick * .4 + seed) + 1) / 2);
  return <AnimatePresence initial={false}>{show && <motion.div key="vitals" className="telemetry-overlay absolute right-5 bottom-20 left-5 z-10" initial={{ opacity: 0, y: reduced ? 0 : motionTokens.distance.sm }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: reduced ? 0 : motionTokens.distance.sm }} transition={{ duration: motionTokens.duration.fast }}>
    <div className="grid max-w-[410px] grid-cols-2 gap-3"><Dial value={heart} max={140} label={t("heart_rate")} unit="bpm" /><Dial value={oxygen} max={100} label={t("oxygen")} unit="%" oxygen /></div>
    <p className="mt-2 text-[9px] text-muted">{t("demo_vitals_hint")}</p>
  </motion.div>}</AnimatePresence>;
}
