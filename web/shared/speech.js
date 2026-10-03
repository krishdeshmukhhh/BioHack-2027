// Non-visual alert paths (NFR-A6): speech, a beep, and vibration. All offline.
// Browsers only allow these after a user gesture, so unlock() runs from the
// "Turn on alerts" tap. navigator.vibrate is missing on iOS Safari and Firefox
// for Android (PRD R7); there the beep and speech still work.

import { currentLang } from "./core.js";

let audio = null;
let unlocked = false;

export const canVibrate = () => typeof navigator.vibrate === "function";
export const canSpeak = () => "speechSynthesis" in window;

export function isUnlocked() {
  return unlocked;
}

/** Call from a click handler. Unlocks audio, speech and vibration for this page. */
export function unlock() {
  try {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (Ctx && !audio) audio = new Ctx();
    audio?.resume();
  } catch {
    audio = null;
  }
  if (canSpeak()) {
    const warm = new SpeechSynthesisUtterance(" ");
    warm.volume = 0;
    speechSynthesis.speak(warm);
  }
  if (canVibrate()) navigator.vibrate(30);
  unlocked = true;
}

/** Prefer an on-device voice in the page language (FR-27, PRD R12). */
function pickVoice(lang) {
  const voices = canSpeak() ? speechSynthesis.getVoices() : [];
  const match = (v) => v.lang && v.lang.toLowerCase().startsWith(lang);
  return (
    voices.find((v) => match(v) && v.localService) ||
    voices.find((v) => match(v)) ||
    null
  );
}

export function speak(text) {
  if (!canSpeak() || !text) return false;
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  const lang = currentLang();
  u.lang = lang;
  const voice = pickVoice(lang);
  if (voice) u.voice = voice;
  speechSynthesis.speak(u);
  return true;
}

/** Two short, soft tones. No flashing, no looping. */
export function beep() {
  if (!audio) return false;
  const now = audio.currentTime;
  for (const [i, freq] of [[0, 660], [1, 520]]) {
    const osc = audio.createOscillator();
    const gain = audio.createGain();
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(0.0001, now + i * 0.35);
    gain.gain.exponentialRampToValueAtTime(0.25, now + i * 0.35 + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + i * 0.35 + 0.3);
    osc.connect(gain).connect(audio.destination);
    osc.start(now + i * 0.35);
    osc.stop(now + i * 0.35 + 0.32);
  }
  return true;
}

export function vibrate() {
  return canVibrate() ? navigator.vibrate([300, 150, 300, 150, 600]) : false;
}

// ---- Optional voice answer (NFR-A5). Only offered when the browser can recognise
// speech ON THE DEVICE: the demo must not send audio to a cloud service.

const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;

export async function canListenOffline() {
  if (!Recognition || typeof Recognition.available !== "function") return false;
  try {
    const status = await Recognition.available({ langs: [currentLang()], processLocally: true });
    return status === "available";
  } catch {
    return false;
  }
}

/** Listen once. Resolves with the lower-cased transcript, or "" if nothing heard. */
export function listenOnce() {
  return new Promise((resolve) => {
    const r = new Recognition();
    r.lang = currentLang();
    r.processLocally = true;
    r.interimResults = false;
    r.maxAlternatives = 3;
    let heard = "";
    r.onresult = (ev) => {
      heard = [...ev.results[0]].map((a) => a.transcript).join(" ").toLowerCase();
    };
    r.onend = () => resolve(heard);
    r.onerror = () => resolve("");
    r.start();
  });
}
