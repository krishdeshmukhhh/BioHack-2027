"use client";
import { useId, useState, type ReactNode } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { ChevronDown, Check, CircleAlert, FlaskConical } from "lucide-react";
import { PolarAngleAxis, RadialBar, RadialBarChart, ResponsiveContainer } from "recharts";
import { useLocale } from "@/lib/locale";
import type { Prescription } from "@/lib/pump";
import { motionTokens } from "@/lib/motion";

export function Accordion({ title, subtitle, icon, children, defaultOpen = false }: { title: string; subtitle?: string; icon: ReactNode; children: ReactNode; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const id = useId();
  const reduced = useReducedMotion();
  return <motion.section layout={reduced ? false : "position"} className="accordion" transition={{ duration: reduced ? 0 : motionTokens.duration.normal, ease: motionTokens.easing.smooth }}>
    <h2><button type="button" aria-expanded={open} aria-controls={id} id={`${id}-heading`} onClick={() => setOpen(!open)} className="flex w-full items-center gap-4 py-6 text-left">
      <span aria-hidden="true" className="text-accent shrink-0">{icon}</span><span className="flex-1 min-w-0"><span className="block text-lg font-semibold tracking-tight">{title}</span>{subtitle && <span className="mt-1 block text-sm font-normal text-muted">{subtitle}</span>}</span>
      <motion.span animate={{ rotate: reduced ? 0 : open ? 180 : 0 }} transition={{ duration: reduced ? 0 : motionTokens.duration.fast }}><ChevronDown size={18} aria-hidden="true" /></motion.span>
    </button></h2>
    <div id={id} role="region" aria-labelledby={`${id}-heading`} aria-hidden={!open} inert={!open}><AnimatePresence initial={false}>{open && <motion.div key="content" initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: reduced ? 0 : motionTokens.duration.normal, ease: motionTokens.easing.smooth }} className="overflow-hidden"><div className="pb-5">{children}</div></motion.div>}</AnimatePresence></div>
  </motion.section>;
}

export function SimLabel() { const { t } = useLocale(); return <span className="inline-flex items-center gap-1.5 rounded-full border border-line px-3 py-1 text-xs font-medium text-muted"><FlaskConical size={13} aria-hidden="true" />{t("simulated_data")}</span>; }

export function RxChip({ rx }: { rx: Prescription }) {
  const { t } = useLocale();
  const label = t(`rx_${rx.state}`);
  return <span className={`inline-flex items-center gap-1.5 rounded-full border border-current px-2.5 py-1 text-xs font-semibold ${rx.state === "rejected" ? "text-danger" : rx.state === "active" ? "text-good" : "text-warm"}`}>
    {rx.state === "active" ? <Check size={13} aria-hidden="true" /> : <CircleAlert size={13} aria-hidden="true" />}{label}
  </span>;
}

export function FeedGauge({ delivered, target }: { delivered: number; target: number }) {
  const { t, number } = useLocale();
  const percent = target > 0 ? Math.max(0, Math.min(100, Math.round(delivered / target * 100))) : 0;
  return <div className="relative mx-auto aspect-square w-full max-w-[360px]" role="progressbar" aria-label={t("progress")} aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent} aria-valuetext={`${number(delivered)} mL / ${number(target)} mL`}>
    <div className="absolute inset-0" aria-hidden="true"><ResponsiveContainer width="100%" height="100%" minWidth={0}>
      <RadialBarChart data={[{ value: percent, fill: "var(--accent)" }]} innerRadius="77%" outerRadius="89%" startAngle={90} endAngle={-270}>
        <PolarAngleAxis type="number" domain={[0, 100]} angleAxisId={0} tick={false} />
        <RadialBar dataKey="value" background={{ fill: "var(--track)" }} cornerRadius={20} isAnimationActive={false} />
      </RadialBarChart>
    </ResponsiveContainer></div>
    <div aria-hidden="true" className="absolute inset-0 flex flex-col items-center justify-center"><span className="font-display text-[76px] leading-none tracking-[-.07em] tabular-nums">{number(percent)}<span className="text-4xl">%</span></span><span className="mt-4 text-sm text-muted">{t("percent")}</span></div>
  </div>;
}
