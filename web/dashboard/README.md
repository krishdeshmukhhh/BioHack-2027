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

Open **http://localhost:3000** for family care or **http://localhost:3000/clinician**
for the clinician workspace. Mock pump controls remain at http://localhost:8003/_mock/.
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
