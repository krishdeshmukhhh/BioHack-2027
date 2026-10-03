# Hub HTTP and SSE API (contract v1 draft)

The contract between the **hub lane** (which implements it) and the **web lane** (which uses it and mocks it). It is frozen in Wave 0 (see `PARALLEL.md`). After that, only the lead changes it, on `main`, and records the change under "Changes" at the bottom.

Prototype rules apply here too: there is no authentication, and users are fixed demo users. All values are demo values.

## Conventions

- JSON in and out, `snake_case`, units in field names, exactly as in `shared/protocol/`.
- Times are ISO-8601 UTC strings set by the hub, for example `"2026-10-03T12:00:00Z"`. Pumps send only `uptime_ms`.
- Errors look like `{"error": "<code>", "detail": "<human text>"}` with a 4xx status. The web app maps the `code` to a string in `strings.<lang>.js`.
- Every response that includes generated or simulated data carries `"simulated": true`.

## Demo users (fixed)

| id | role | display |
|---|---|---|
| `clin-01` | clinician | Dr. Demo |
| `care-01` | parent | Parent (demo) |
| `care-02` | school_nurse | School nurse (demo) |

## Objects

**PumpStatus**: the latest `status` message plus fields added by the hub:

```json
{
  "pump_id": "pump-001", "state": "running", "rate_ml_hr": 60, "delivered_ml": 120.5,
  "target_ml": 500, "alarm": null, "prescription_version": 7, "pending_version": null,
  "battery_pct": 80, "simulated": true,
  "online": true, "received_at": "2026-10-03T12:00:00Z"
}
```

**Prescription**:

```json
{
  "pump_id": "pump-001", "version": 8, "mode": "continuous", "rate_ml_hr": 90, "volume_ml": 500,
  "note": "", "state": "sent", "reject_reason": null,
  "proposed_by": "clin-01", "proposed_at": "…", "confirmed_by": "care-01", "confirmed_role": "parent",
  "confirmed_at": "…", "sent_at": "…", "resolved_at": null
}
```

- `state` is one of: `proposed` | `confirmed` | `sent` | `active` | `rejected` | `superseded`.
- `reject_reason` is one of the pump reasons in `event.schema.json`, or `declined` (caregiver).

**Alert**: a hub-side interpretation of a pump alarm.

```json
{ "pump_id": "pump-001", "alarm": "occlusion", "active": true, "raised_at": "…", "cleared_at": null }
```

The web app maps `alarm` to the picture, cause, and steps in its strings file. The hub sends the code, not the copy.

**AuditRow**:

```json
{ "id": 42, "at": "…", "actor": "care-01", "actor_role": "parent", "entity": "prescription",
  "entity_id": "pump-001/8", "action": "confirmed", "old_value": "proposed", "new_value": "confirmed" }
```

## Endpoints

| Method | Path | Body | 200 response | Errors |
|---|---|---|---|---|
| GET | `/health` | — | `{"status":"ok"}` | — |
| GET | `/api/pumps/{pump_id}/status` | — | PumpStatus | 404 `unknown_pump`; 200 with `online:false` if no data yet |
| GET | `/api/pumps/{pump_id}/prescriptions` | — | `[Prescription]`, newest first | 404 |
| POST | `/api/pumps/{pump_id}/prescriptions` | `{mode, rate_ml_hr, volume_ml, note?, proposed_by}` | Prescription (`proposed`, new version) | 422 `invalid_input` (shape only; **no limit check here**, S1 lives in the pump) |
| POST | `/api/pumps/{pump_id}/prescriptions/{version}/confirm` | `{confirmed_by}` | Prescription (`sent`, or `confirmed` if the publish failed) | 404; 409 `not_proposed` |
| POST | `/api/pumps/{pump_id}/prescriptions/{version}/decline` | `{declined_by, reason?}` | Prescription (`rejected`, `reject_reason:"declined"`) | 404; 409 `not_proposed` |
| GET | `/api/pumps/{pump_id}/alerts` | — | `[Alert]` (active first) | 404 |
| GET | `/api/pumps/{pump_id}/audit` | — | `[AuditRow]`, newest first | 404 |
| GET | `/api/patients` | — | `[{id, display_name, pump_id, exceptions:[string], online, simulated}]`, exceptions first | — |
| GET | `/api/patients/{id}/daily` | `?days=30` | `[{date, delivered_ml, prescribed_ml, alarm_count, simulated}]` | 404 |
| GET | `/api/pumps/{pump_id}/stream` | — | SSE (below) | 404 |

Web pages are served at `/` (family app, `web/family/`) and `/clinician/` (`web/clinician/`).

## SSE stream `/api/pumps/{pump_id}/stream`

Uses `text/event-stream`. Each message has an `event:` name and a JSON `data:` field. On connect, the hub immediately sends one `status`, one `availability`, and one `prescription` for every non-final version, so the page renders without making extra requests.

| event | data | When |
|---|---|---|
| `status` | PumpStatus | Every pump status (~2 s) |
| `availability` | `{"pump_id", "online": bool, "last_seen_at"}` | On change |
| `prescription` | Prescription | On every lifecycle change |
| `alert` | Alert | Raised or cleared |
| `pump_event` | The raw `event` message plus `received_at` | Every pump event (for timelines) |

The browser uses `EventSource`, which reconnects automatically. After a reconnect, the initial snapshot brings the page back in sync.

## Changes

- (none yet)
