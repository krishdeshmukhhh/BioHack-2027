# Hub HTTP and SSE API (contract v1, frozen)

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

Optional status fields pass through when the pump sends them: `battery_pct`, `level_pct`, `last_rejected_version`, and `last_reject_reason` (see `docs/PROTOCOL.md`). The web app must not use the last two to drive the chip. The hub folds them into the Prescription `state`, and the chip reads only that.

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
{ "pump_id": "pump-001", "alarm": "occlusion", "active": true, "raised_at": "…", "cleared_at": null, "simulated": true }
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
| POST | `/api/pumps/{pump_id}/prescriptions/{version}/confirm` | `{confirmed_by}` | Prescription (`sent`, or `confirmed` if the publish failed) | 404; 409 `not_proposed`; 409 `stale_version` (a newer version was already published, S3) |
| POST | `/api/pumps/{pump_id}/prescriptions/{version}/decline` | `{declined_by, reason?}` | Prescription (`rejected`, `reject_reason:"declined"`) | 404; 409 `not_proposed` |
| GET | `/api/pumps/{pump_id}/alerts` | — | `[Alert]` (active first) | 404 |
| GET | `/api/pumps/{pump_id}/audit` | — | `[AuditRow]`, newest first | 404 |
| GET | `/api/patients` | — | `[{id, display_name, pump_id, exceptions:[string], online, simulated}]`, exceptions first | — |
| GET | `/api/patients/{id}/daily` | `?days=30` | `[{date, delivered_ml, prescribed_ml, alarm_count, simulated}]` | 404 |
| GET | `/api/patients/{id}/summary` | — | WeeklySummary (below) | 404 |
| GET | `/api/patients/{id}/profiles` | — | `[{id, patient_id, name, mode, rate_ml_hr, volume_ml, simulated}]`, demo feed profiles that pre-fill the propose form (FR-28) | 404 |
| GET | `/api/pumps/{pump_id}/stream` | — | SSE (below) | 404 |

`/api/patients` exception codes (demo thresholds, not clinical guidance):

| code | Rule |
|---|---|
| `offline` | No pump status received in the last 10 s, or availability is `offline` |
| `under_target` | `delivered_ml` below 90% of `prescribed_ml` on each of the last 3 days |
| `night_alarms` | More than 2 alarms raised in the most recent night window (22:00 to 06:00 UTC). A repeated QoS 1 event counts once |
| `alarm_active` | The pump's latest status has a non-null `alarm` (the portal flag for a live alarm) |

Web pages are served at `/` (family app, `web/family/`) and `/clinician/` (`web/clinician/`). Files used by both apps (tokens, strings, shared modules) are served at `/shared/` (`web/shared/`).

## SSE stream `/api/pumps/{pump_id}/stream`

Uses `text/event-stream`. Each message has an `event:` name and a JSON `data:` field. On connect, the hub immediately sends one `status`, one `availability`, one `prescription` for every non-final version, and one `alert` for every active alert, so the page renders without making extra requests.

| event | data | When |
|---|---|---|
| `status` | PumpStatus | Every pump status (~2 s) |
| `availability` | `{"pump_id", "online": bool, "last_seen_at"}` | On change |
| `prescription` | Prescription | On every lifecycle change |
| `alert` | Alert | Raised or cleared |
| `pump_event` | The raw `event` message plus `received_at` | Every pump event (for timelines) |

The browser uses `EventSource`, which reconnects automatically. After a reconnect, the initial snapshot brings the page back in sync.

**WeeklySummary** (FR-21): facts only, as codes and numbers. The web app words them from its strings file.

```json
{"patient_id": "pat-01", "from_date": "2026-09-27", "to_date": "2026-10-03", "days": 7,
 "delivered_pct": 97.5, "prior_week_delivered_pct": 98.1, "trend": "steady",
 "days_under_target": 0, "alarm_count": 1, "alarms_by_code": {"bag_empty": 1}, "simulated": true}
```

With no history loaded, `days` is 0 and the percentages and `trend` are null.

## History file (sim to hub hand-off)

`make history` writes `sim/data/history.json` (gitignored; regenerate before the demo so the dates end today). The hub loads it into its database for `/api/patients` and `/api/patients/{id}/daily`.

```json
{"simulated": true, "seed": 2026, "generated_for_end_date": "2026-10-03",
 "patients": [{"id": "pat-01", "display_name": "Demo Child Aster", "pump_id": "pump-001", "pattern": "on_target", "simulated": true}],
 "daily": [{"patient_id": "pat-01", "pump_id": "pump-001", "date": "2026-10-03", "delivered_ml": 880.0, "prescribed_ml": 900.0, "alarm_count": 0, "simulated": true}],
 "alarms": [{"patient_id": "pat-01", "pump_id": "pump-001", "alarm": "bag_empty", "raised_at": "2026-09-04T11:57:00Z", "cleared_at": "2026-09-04T12:07:00Z", "simulated": true}]}
```

`pattern` is a label for people. The hub computes exceptions from the rows, not from `pattern`. `alarm_count` counts by the UTC date of `raised_at`.

## Changes

- 2026-10-03 `contract-v1` frozen. PumpStatus documents the optional pass-through fields, including the R1 reject fields.
- 2026-10-03 Additive: exception codes and thresholds for `/api/patients`, and the history file format.
- 2026-10-03 Additive: `/shared/` serves `web/shared/` (found at Sync 1: the family page imports `/shared/*.js`).
- 2026-10-03 (Sync 2) Additive: `summary` and `profiles` endpoints (as built by the hub lane), the `alarm_active` exception code, active alerts in the SSE snapshot, and the rule that a repeated event counts once.
- 2026-10-03 (Sync 2 review): confirm may return 409 `stale_version`; Alert carries `simulated`.
