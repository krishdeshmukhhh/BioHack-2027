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
