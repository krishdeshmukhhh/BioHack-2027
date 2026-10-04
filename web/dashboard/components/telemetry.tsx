"use client";
import { useEffect, useState } from "react";
import { animate, motion, useMotionValue, useReducedMotion, useTransform } from "framer-motion";
import { Heart, Wind } from "lucide-react";
import { PolarAngleAxis, RadialBar, RadialBarChart, ResponsiveContainer } from "recharts";
import { motionTokens } from "@/lib/motion";
import { useLocale } from "@/lib/locale";
import type { Patient, Pump } from "@/lib/pump";

export function VitalGauge({ value, max, label, unit, oxygen = false }: {
  value: number | null; max: number; label: string; unit: string; oxygen?: boolean;
}) {
  const { t } = useLocale();
  const reduced = useReducedMotion();
  const animated = useMotionValue(0);
  const display = useTransform(animated, (number) => Math.round(number));
  useEffect(() => {
    const controls = animate(animated, value ?? 0, { duration: reduced ? 0 : motionTokens.duration.telemetry, ease: motionTokens.easing.smooth });
    return () => controls.stop();
  }, [value, animated, reduced]);
  return <section className="semi-gauge min-w-0 rounded-xl border border-line bg-panel px-2 pt-3 pb-2" role="img" aria-label={value == null ? `${label}: ${t("vitals_unavailable")}` : `${label}: ${value} ${unit} · ${t("simulated_data")}`}>
    <h3 className="flex items-center justify-center gap-1.5 text-[11px] font-medium text-muted">{oxygen ? <Wind size={13} aria-hidden="true" /> : <Heart size={13} aria-hidden="true" />}{label}</h3>
    <div className="semi-chart relative mt-1 h-[112px]" aria-hidden="true">
      <ResponsiveContainer width="100%" height="100%" minWidth={0}>
        <RadialBarChart data={[{ value: value ?? 0, fill: "var(--accent)" }]} cx="50%" cy="80%" innerRadius="74%" outerRadius="94%" startAngle={180} endAngle={0}>
          <PolarAngleAxis type="number" domain={[0, max]} tick={false} />
          <RadialBar dataKey="value" background={{ fill: "var(--track)" }} cornerRadius={8} isAnimationActive={!reduced && value != null} animationBegin={0} animationDuration={motionTokens.duration.telemetry * 1000} />
        </RadialBarChart>
      </ResponsiveContainer>
      <div className="gauge-value absolute inset-x-0 bottom-3 flex flex-col items-center"><span className="text-[30px] leading-none font-medium tabular-nums">{value == null ? "—" : <motion.span>{display}</motion.span>}</span><span className="mt-1 text-[9px] text-muted">{unit}</span></div>
      <div className="absolute inset-x-1 bottom-0 flex justify-between text-[8px] text-muted"><span>0</span><span>{max}</span></div>
    </div>
  </section>;
}

export function PatientTelemetry({ patient, pump, enabled }: { patient?: Patient; pump: Pump; enabled: boolean }) {
  const { t } = useLocale();
  const [tick, setTick] = useState(0);
  // HR and SpO2 are absent from the pump API. A real source always displays unavailable.
  const show = enabled && pump.status?.simulated === true && patient?.simulated === true;
  useEffect(() => {
    if (!show) return;
    const interval = setInterval(() => setTick((value) => value + 1), 2500);
    return () => clearInterval(interval);
  }, [show]);
  const seed = Array.from(pump.pumpId).reduce((sum, c) => sum + c.charCodeAt(0), 0);
  const heart = show ? 72 + seed % 12 + Math.round(Math.sin(tick * .7) * 4) : null;
  const oxygen = show ? 97 + Math.round((Math.sin(tick * .4 + seed) + 1) / 2) : null;
  return <div className="patient-telemetry shrink-0 px-5 py-3" aria-label={t("patient_vitals")}>
    <div className="grid grid-cols-2 gap-3"><VitalGauge value={heart} max={140} label={t("heart_rate")} unit="bpm" /><VitalGauge value={oxygen} max={100} label={t("oxygen")} unit="%" oxygen /></div>
    <p className="mt-2 text-[9px] text-muted">{t(show ? "demo_vitals_hint" : "vitals_unavailable")}</p>
  </div>;
}
