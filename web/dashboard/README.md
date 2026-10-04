# React care dashboard

Next.js App Router, React, Tailwind CSS, Recharts, Framer Motion, and Lucide icons.
All assets are bundled locally; the running dashboard needs no CDN or internet.

From the repository root, start the simulated backend in one terminal:

```powershell
python web/_mock/mock_api.py
```

Start the dashboard in a second terminal:

```powershell
cd web/dashboard
npm ci
npm run dev
```

Open **http://localhost:3000** for the ward command dashboard or
**http://localhost:3000/clinician** to open it with the Orders tab selected.
Mock pump controls remain at http://localhost:8003/_mock/.
The older static pages run on port 8003; the React dashboard runs on port 3000.

The Next.js API route forwards HTTP and SSE to `HUB_URL`, defaulting to
`http://127.0.0.1:8003`. To connect to the real hub, copy `.env.example` to
`.env.local`, change `HUB_URL`, and restart Next.js. This requires a Node.js
process alongside the Python hub; it is not served by the hub's static-file mount.
Use Node.js 22 LTS or newer.

Production and verification:

```powershell
npm run typecheck
npm run build
npm start
```

The shared hub data store remains authoritative for prescription chips.
Confirm/decline HTTP responses do not mark prescriptions active; pump-originated
SSE telemetry does. Changing patients closes the previous stream. Accordion
animations respect reduced motion, and charts have readable labels and tables.

## Single-screen interaction

The shell fits `100dvh` and locks document scrolling. Global and Ward Map show
clickable bed markers. Patients and Alerts swap the central pane for searchable,
paginated rosters. The map is a schematic demo layout, not patient location data.

Selecting a bed opens the adjacent patient panel. Close it to expand the map;
Escape also closes it and restores keyboard focus. On screens up to 900px wide,
the map and details occupy the same space and clicking swaps between them.

Monitor, Care, Orders, and History tabs keep exploration in the same viewport.
Care contains caregiver review and alert preferences; Orders contains proposal
controls. History has Delivery, Prescriptions, and Audit tabs. Arrow keys, Home,
and End navigate each tab group. Deep content scrolls only inside its panel.

The charcoal and teal theme is bundled in Tailwind tokens. Framer Motion drives
grid resizing, shared `layoutId` selection/panel transitions, tabs, accordions,
and number updates; motion tokens live in `lib/motion.ts`.

Heart rate and oxygen overlays are **synthetic demo values**, independently
labelled as simulated. The pump API does not measure these vitals. They appear
only when both the selected patient and pump telemetry explicitly report
`simulated: true`; the Demo vitals button toggles them. Real pump sources never
receive fabricated vital signs. Feed progress and prescription state always
come from the existing hub REST/SSE connection.
