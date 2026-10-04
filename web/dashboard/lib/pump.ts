"use client";

import { useEffect, useState } from "react";
import { api, createPumpStore, KNOWN_ERRORS } from "../../shared/data.js";

export { api };

/** Strings key for an API error: a known code, else generic. Never a bare code. */
export function errorKey(err: unknown): string {
  const code = (err as { code?: string } | null)?.code;
  return code && (KNOWN_ERRORS as string[]).includes(code) ? `error_${code}` : "error_generic";
}
export type Prescription = {
  version: number; state: string; mode: string; rate_ml_hr: number; volume_ml: number;
  note?: string; reject_reason?: string; confirmed_by?: string; confirmed_role?: string;
  proposed_at?: string; resolved_at?: string;
};
export type Alert = { alarm: string; active: boolean; raised_at: string; cleared_at?: string; simulated?: boolean };
export type Patient = { id: string; display_name: string; pump_id: string; exceptions: string[]; simulated: boolean; online: boolean };
export type Daily = { date: string; delivered_ml: number; prescribed_ml: number; alarm_count: number; simulated: boolean };
export type Profile = { id: string; name: string; mode: string; rate_ml_hr: number; volume_ml: number; simulated: boolean };
export type Audit = { id: number; at: string; actor: string; actor_role: string; action: string; entity_id: string };
export type Summary = { days: number; delivered_pct: number; days_under_target: number; alarm_count: number; trend: string; simulated: boolean };
export type Pump = {
  pumpId: string; stream: string; online: boolean; lastUpdateAt: string | null;
  availability: { online: boolean; last_seen_at: string | null };
  status: { received_at?: string; state: string; alarm?: string; delivered_ml: number; target_ml: number; rate_ml_hr: number; prescription_version: number; simulated: boolean } | null;
  prescriptions: Record<number, Prescription>; alerts: Alert[];
  history: { at: string; delivered_ml: number; target_ml: number }[];
};
const empty: Pump = {
  pumpId: "pump-001", stream: "connecting", online: false, lastUpdateAt: null,
  availability: { online: false, last_seen_at: null }, status: null, prescriptions: {}, alerts: [], history: [],
};

export function usePump(id: string) {
  const [snapshot, setSnapshot] = useState<Pump>({ ...empty, pumpId: id });
  useEffect(() => {
    setSnapshot({ ...empty, pumpId: id });
    const store = createPumpStore(id);
    const unsubscribe = store.subscribe((value: unknown) => {
      const state = value as Pump;
      setSnapshot({ ...state, prescriptions: { ...state.prescriptions }, alerts: [...state.alerts], history: [...state.history] });
    });
    store.start();
    return () => { unsubscribe(); store.stop(); };
  }, [id]);
  return snapshot.pumpId === id ? snapshot : { ...empty, pumpId: id };
}

export function useResource<T>(path: string | null, refreshMs = 0) {
  const [result, setResult] = useState<{ path: string | null; data: T | null; error: boolean }>({ path: null, data: null, error: false });
  useEffect(() => {
    if (!path) return;
    const controller = new AbortController();
    let inFlight = false;
    async function load() {
      if (inFlight) return;
      inFlight = true;
      try {
        const response = await fetch(path!, { cache: "no-store", signal: controller.signal });
        if (!response.ok) throw new Error("Unavailable");
        const data = await response.json() as T;
        if (!controller.signal.aborted) setResult({ path, data, error: false });
      } catch {
        if (!controller.signal.aborted) setResult((previous) => ({ path, data: previous.path === path ? previous.data : null, error: true }));
      } finally { inFlight = false; }
    }
    load();
    const timer = refreshMs ? setInterval(load, refreshMs) : null;
    return () => { controller.abort(); if (timer) clearInterval(timer); };
  }, [path, refreshMs]);
  return result.path === path ? result : { path, data: null, error: false };
}
