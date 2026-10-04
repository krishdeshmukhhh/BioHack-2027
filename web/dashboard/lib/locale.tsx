"use client";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import en from "../../shared/strings.en.js";
import es from "../../shared/strings.es.js";
import { wardCopy } from "./ward-copy";

const extra = {
  en: { workspace: "Care workspace", overview: "Overview", family: "Family", clinician: "Clinician", feed_session: "This feed", delivery: "Delivery", remaining: "Remaining", feed_settings: "Feed settings", recent_activity: "Recent activity", pump_status: "Pump status", nothing_waiting: "You’re all caught up", review_hint: "No prescription changes waiting for review.", settings_hint: "Language, caregiver & alert preferences", alert_hint: "Clear instructions when the pump needs attention", live: "Live", dark: "Night", light: "Day", connected: "Connected", disconnected: "Offline", unknown: "Waiting for pump", data_stale: "Showing the last received reading.", alert_ack: "Acknowledged on this device", enable: "Enable alerts", details: "Details", percent: "of feed delivered", patient_hint: "Select a patient to inspect their feed", history: "Delivery history", new_proposal: "New proposal", patient_count: "patients", attention_count: "need attention", read: "Read aloud", current: "Current", progress: "Feed progress" },
  es: { workspace: "Espacio de cuidados", overview: "Resumen", family: "Familia", clinician: "Personal clínico", feed_session: "Esta alimentación", delivery: "Administrado", remaining: "Restante", feed_settings: "Ajustes de alimentación", recent_activity: "Actividad reciente", pump_status: "Estado de la bomba", nothing_waiting: "Todo al día", review_hint: "No hay cambios de prescripción pendientes.", settings_hint: "Idioma, cuidador y preferencias de alertas", alert_hint: "Instrucciones claras cuando la bomba necesita atención", live: "En vivo", dark: "Noche", light: "Día", connected: "Conectada", disconnected: "Sin conexión", unknown: "Esperando la bomba", data_stale: "Se muestra la última lectura recibida.", alert_ack: "Confirmada en este dispositivo", enable: "Activar alertas", details: "Detalles", percent: "de la alimentación administrada", patient_hint: "Seleccione un paciente para revisar su alimentación", history: "Historial de alimentación", new_proposal: "Nueva propuesta", patient_count: "pacientes", attention_count: "necesitan atención", read: "Leer en voz alta", current: "Actual", progress: "Progreso de alimentación" },
};
type Locale = { lang: "en" | "es"; setLang: (value: "en" | "es") => void; t: (key: string, vars?: Record<string, string | number>) => string; list: (key: string) => string[]; user: (id: string) => string; number: (value: number) => string; date: (value?: string | null) => string };
const Context = createContext<Locale | null>(null);
export function LocaleProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<"en" | "es">("en");
  useEffect(() => { try { if (localStorage.getItem("sp-lang") === "es") setLang("es"); } catch { /* session only */ } }, []);
  useEffect(() => { document.documentElement.lang = lang; try { localStorage.setItem("sp-lang", lang); } catch { /* session only */ } }, [lang]);
  const strings = { ...en, ...(lang === "es" ? es : {}), ...extra[lang], ...wardCopy[lang] } as Record<string, unknown>;
  const t = (key: string, vars: Record<string, string | number> = {}) => String(strings[key] ?? key).replace(/\{(\w+)\}/g, (match, name: string) => String(vars[name] ?? match));
  const value: Locale = {
    lang, setLang, t,
    list: (key) => Array.isArray(strings[key]) ? strings[key] as string[] : [],
    user: (id) => (strings.users as Record<string, string>)[id] || id,
    number: (value) => value.toLocaleString(lang, { maximumFractionDigits: 1 }),
    date: (value) => value ? new Date(value).toLocaleString(lang, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : t("never_updated"),
  };
  return <Context.Provider value={value}>{children}</Context.Provider>;
}
export function useLocale() { return useContext(Context)!; }
