-- Hub SQLite schema. Prototype, all data fictional. See docs/research/ARCHITECTURE-DIAGRAMS.md §9.

CREATE TABLE IF NOT EXISTS patients (
    id            TEXT PRIMARY KEY,
    display_name  TEXT NOT NULL,          -- fictional
    pump_id       TEXT NOT NULL UNIQUE,
    daily_goal_ml REAL,                   -- demo value
    simulated     INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS prescriptions (
    id             INTEGER PRIMARY KEY,
    pump_id        TEXT NOT NULL,
    version        INTEGER NOT NULL,      -- per pump, only goes up (S3)
    mode           TEXT NOT NULL CHECK (mode IN ('continuous', 'bolus')),
    rate_ml_hr     REAL NOT NULL,
    volume_ml      REAL NOT NULL,
    note           TEXT NOT NULL DEFAULT '',
    state          TEXT NOT NULL CHECK (state IN
                     ('proposed', 'confirmed', 'sent', 'active', 'rejected', 'superseded')),
    reject_reason  TEXT,
    proposed_by    TEXT NOT NULL,
    proposed_at    TEXT NOT NULL,
    confirmed_by   TEXT,
    confirmed_role TEXT,
    confirmed_at   TEXT,
    sent_at        TEXT,
    resolved_at    TEXT,
    UNIQUE (pump_id, version)
);

CREATE TABLE IF NOT EXISTS status_samples (
    id                   INTEGER PRIMARY KEY,
    pump_id              TEXT NOT NULL,
    received_at          TEXT NOT NULL,   -- hub wall clock
    uptime_ms            INTEGER NOT NULL,
    state                TEXT NOT NULL,
    rate_ml_hr           REAL NOT NULL,
    delivered_ml         REAL NOT NULL,
    target_ml            REAL NOT NULL,
    alarm                TEXT,
    prescription_version INTEGER NOT NULL,
    pending_version      INTEGER,
    battery_pct          INTEGER,
    level_pct            REAL,
    last_rejected_version INTEGER,
    last_reject_reason   TEXT,
    simulated            INTEGER NOT NULL,
    raw                  TEXT NOT NULL    -- the validated message as received
);
CREATE INDEX IF NOT EXISTS status_samples_pump ON status_samples (pump_id, id);

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY,
    pump_id     TEXT NOT NULL,
    received_at TEXT NOT NULL,
    uptime_ms   INTEGER NOT NULL,
    type        TEXT NOT NULL,
    version     INTEGER,
    reason      TEXT,
    alarm       TEXT,
    from_state  TEXT,
    to_state    TEXT,
    simulated   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS events_pump ON events (pump_id, id);

-- Append-only (S7): the triggers below make UPDATE and DELETE fail in the database itself.
CREATE TABLE IF NOT EXISTS audit (
    id         INTEGER PRIMARY KEY,
    at         TEXT NOT NULL,
    actor      TEXT NOT NULL,             -- user id or pump id
    actor_role TEXT NOT NULL,
    entity     TEXT NOT NULL,             -- prescription, alarm, profile
    entity_id  TEXT NOT NULL,
    action     TEXT NOT NULL,
    old_value  TEXT,
    new_value  TEXT
);

CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit
BEGIN
    SELECT RAISE(ABORT, 'audit is append-only');
END;

CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit
BEGIN
    SELECT RAISE(ABORT, 'audit is append-only');
END;

-- Live alerts: the hub's reading of pump alarms (FR-14, FR-15). At most one open per code.
CREATE TABLE IF NOT EXISTS alerts (
    id         INTEGER PRIMARY KEY,
    pump_id    TEXT NOT NULL,
    alarm      TEXT NOT NULL,
    raised_at  TEXT NOT NULL,             -- hub wall clock
    cleared_at TEXT,
    simulated  INTEGER NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS alerts_open ON alerts (pump_id, alarm) WHERE cleared_at IS NULL;

-- Generated 30-day history from sim/data/history.json (docs/API.md). Every row simulated (S8).
CREATE TABLE IF NOT EXISTS history_daily (
    patient_id    TEXT NOT NULL REFERENCES patients (id),
    date          TEXT NOT NULL,
    delivered_ml  REAL NOT NULL,
    prescribed_ml REAL NOT NULL,
    alarm_count   INTEGER NOT NULL,
    simulated     INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (patient_id, date)
);

CREATE TABLE IF NOT EXISTS history_alarms (
    id         INTEGER PRIMARY KEY,
    patient_id TEXT NOT NULL REFERENCES patients (id),
    alarm      TEXT NOT NULL,
    raised_at  TEXT NOT NULL,
    cleared_at TEXT,
    simulated  INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS profiles (
    id         INTEGER PRIMARY KEY,
    patient_id TEXT NOT NULL REFERENCES patients (id),
    name       TEXT NOT NULL,
    mode       TEXT NOT NULL,
    rate_ml_hr REAL NOT NULL,             -- demo value
    volume_ml  REAL NOT NULL              -- demo value
);
