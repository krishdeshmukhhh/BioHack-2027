---
paths:
  - "web/**"
---

# Web rules (clinician portal and family app)

## Stack

- Static HTML, CSS, and vanilla JavaScript. No framework, no bundler, no CDN. Everything is served by the hub and must work offline.
- Talk to the hub over HTTP only (plus server-sent events for live updates). Never connect to MQTT from the browser.

## Accessibility (family app especially)

- Mobile first. Touch targets at least 48 by 48 px. Body text at least 18 px.
- Colour contrast at least 4.5 to 1. Never use colour alone to carry meaning; pair it with an icon and text.
- Semantic HTML, labelled controls, visible focus, full keyboard operation. Live status uses `aria-live`.
- All user-facing text comes from a strings file (`strings.<lang>.js`) so languages can be added. Ship English plus one more.
- Alerts say what happened and what to do, in plain language, with a picture where it helps. No error codes on their own.
- Provide a night mode (dim, low blue, no flashing) and respect `prefers-reduced-motion`.
- Alarms have a visual and a vibration path (`navigator.vibrate`), not sound only.
- Voice: use speech synthesis for spoken status (works offline). Treat speech recognition as optional and always provide a button for the same action.

## Honesty in the UI

- Show a prescription as "Pending", "Sent", "Active on pump", or "Rejected" exactly as the hub reports it (S5).
- When the pump is offline, say so clearly and show the time of the last update.
- Any screen showing simulated or generated data shows a visible "Simulated data" label (S8).
- Show a "Prototype, not for clinical use" footer on every page.
