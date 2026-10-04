# React care dashboard

Next.js App Router, React, Tailwind CSS, Recharts, Framer Motion, and Lucide icons.
All assets are bundled locally; the running dashboard needs no CDN or internet.

**For the demo** it runs in Docker with the hub: `make docker-up` from the repository
root, then open **http://<hub-laptop-ip>:3000** (family) or **/clinician** on any device
on the demo network.

**Without Docker**, against the real hub (`make broker`, `make hub`, then a pump):

```bash
cd web/dashboard
npm ci                      # once, while online
HUB_URL=http://127.0.0.1:8000 npm run dev
```

`HUB_URL` is required. There is no default, so the dashboard never shows mock data as if
it were the real pump. For UI work against the mock (`python web/_mock/mock_api.py`),
set `HUB_URL=http://127.0.0.1:8003` explicitly; mock pump controls are at
http://localhost:8003/_mock/. The dev and production servers listen on `0.0.0.0`, so
phones on the same network can reach port 3000 (allow it in the firewall).

The API route forwards HTTP and SSE for `/api/pumps/*` and `/api/patients/*` only.
Use Node.js 22 LTS or newer. The hub-served static pages (port 8000) remain the
fallback UI.

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

The shell fits `100dvh` and locks document scrolling. The clinician overview and Homes show
clickable home markers. Patients and Alerts swap the central pane for searchable,
paginated rosters. The network is schematic; connections represent remote care, not geographic
locations or a shared ward. The family view focuses on one child and includes a
labelled demo household selector.

The clinician dashboard starts with the home network expanded. Selecting a home slides the adjacent
patient panel in from the right. Close it to expand the map and smoothly reset
the camera to the full home network;
Escape also closes it and restores keyboard focus. On screens up to 900px wide,
the map and details occupy the same space and clicking swaps between them.

Family Monitor, Care, and History tabs and clinician Monitor, Orders, and History tabs keep exploration in the same viewport.
Care contains caregiver review and alert preferences; Orders contains proposal
controls. Both views have delivery and prescription history; only clinicians see Audit. Arrow keys, Home,
and End navigate each tab group. Deep content scrolls only inside its panel.

The charcoal and teal theme is bundled in Tailwind tokens. Framer Motion drives
grid resizing, shared `layoutId` selection/panel transitions, tabs, accordions,
and number updates; motion tokens live in `lib/motion.ts`.

Heart rate and oxygen gauges are **synthetic demo values**, independently
labelled as simulated. The pump API does not measure these vitals. Values appear
only when both the selected patient and pump telemetry explicitly report
`simulated: true`; the Demo vitals button toggles them. Real pump sources never
receive fabricated vital signs; their gauges show unavailable. Feed progress and prescription state always
come from the existing hub REST/SSE connection.

## Spatial map and themes

Drag within the home network to pan. Use the mouse wheel, a two-finger pinch, or the
plus/minus controls to zoom between 100% and 350%. Zoom follows the cursor or
pinch midpoint; camera bounds prevent panning beyond the network. The fit button
restores the full map. When the map region has keyboard focus, `+`, `-`, and `0`
zoom in, zoom out, and fit all homes.

Click a home (or press Enter/Space on its button) to select its pump, center the
camera, and open the parent details pane. Pointer movement beyond the drag
threshold suppresses selection, so a drag or pinch cannot accidentally choose
a patient. Bed tags appear on hover/focus or at 180% zoom: the selected pump's
feed rate is hub-backed; synthetic HR tags are explicitly labelled Demo.

Teal indicates selection, red an active alarm, and amber a patient review flag.
Pulse and hover animations respect reduced-motion preferences. The header's
sun/moon button switches between light and dark themes and remembers the choice
on this device. Map walls, telemetry charts, controls, and details share theme
tokens; dark is the default when no preference is stored.

## Cohesive patient pane

`components/patient-details.tsx` exports `PatientDetailsPane`, including its
`AnimatePresence` entrance/exit wrapper. Its pinned header names the patient and
shows pump-alarm/connection status rather than inferring clinical stability.
Immediately below it, `PatientTelemetry` renders a two-column grid of Recharts
semi-circle speedometer gauges; arcs and numbers animate from zero on mount.

The Monitor tab combines feed progress, an expandable active feeding order (rate,
volume, prescribing clinician), current alerts with caregiver instructions,
and connection details. The existing protocol has feeding prescriptions, not
medication records; no medication names or doses are invented. Accordion cards
animate their expansion and the positions of cards below them. Deep content
uses the pane's hidden internal scrollbar; the header, gauges, and tabs stay pinned.

The pane is bounded to its parent grid height, including compact landscape
layouts. Selecting another patient remounts its gauges and closes the previous
telemetry subscription. Close and Escape animate the pane out, while the parent
grid expands the map. Reduced motion disables sliding, gauge, and accordion
animations.

Camera bounds, zoom anchors, and fit behavior have dependency-free tests under
`tests/map-camera.test.mjs`; run them with `npm test` (Node.js 22.6 or newer).
