from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS gnss_samples (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp      TEXT NOT NULL,
    fix_type       INTEGER,
    num_sv         INTEGER,
    lat            REAL,
    lon            REAL,
    alt_m          REAL,
    h_acc_m        REAL,
    v_acc_m        REAL,
    pdop           REAL,
    spoof_det_state INTEGER
);

CREATE TABLE IF NOT EXISTS satellite_metrics (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_id  INTEGER REFERENCES gnss_samples(id) ON DELETE CASCADE,
    timestamp  TEXT NOT NULL,
    gnss_id    INTEGER,
    sv_id      INTEGER,
    cn0_dbhz   REAL,
    elev_deg   REAL,
    azim_deg   REAL,
    quality_ind INTEGER
);

CREATE TABLE IF NOT EXISTS rf_metrics (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp        TEXT NOT NULL,
    block_id         INTEGER,
    jamming_state    INTEGER,
    agc_cnt          INTEGER,
    noise_per_ms     INTEGER,
    jamming_indicator INTEGER,
    ant_status       INTEGER,
    ant_power        INTEGER
);

CREATE TABLE IF NOT EXISTS sec_sig_metrics (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_id        INTEGER REFERENCES gnss_samples(id) ON DELETE CASCADE,
    timestamp        TEXT NOT NULL,
    jamming_state    INTEGER,
    spoofing_state   INTEGER,
    jam_det_enabled  INTEGER,
    spf_det_enabled  INTEGER,
    frequencies_json TEXT
);

CREATE TABLE IF NOT EXISTS signal_metrics (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_id   INTEGER REFERENCES gnss_samples(id) ON DELETE CASCADE,
    timestamp   TEXT NOT NULL,
    gnss_id     INTEGER,
    sv_id       INTEGER,
    sig_id      TEXT,
    cno_dbhz    REAL,
    quality_ind INTEGER,
    health      INTEGER,
    pr_used     INTEGER,
    auth_status INTEGER
);

CREATE TABLE IF NOT EXISTS baseline_stats (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    computed_at    TEXT NOT NULL,
    duration_hours REAL,
    sample_count   INTEGER,
    metric         TEXT NOT NULL,
    mean           REAL,
    stddev         REAL,
    min_val        REAL,
    max_val        REAL
);

CREATE TABLE IF NOT EXISTS events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp     TEXT NOT NULL,
    event_type    TEXT NOT NULL,
    severity      TEXT NOT NULL,
    attribution   TEXT,
    details       TEXT,
    metric_values TEXT,
    resolved_at   TEXT
);

CREATE INDEX IF NOT EXISTS idx_gnss_ts   ON gnss_samples(timestamp);
CREATE INDEX IF NOT EXISTS idx_sat_ts    ON satellite_metrics(timestamp);
CREATE INDEX IF NOT EXISTS idx_rf_ts     ON rf_metrics(timestamp);
CREATE INDEX IF NOT EXISTS idx_secsig_ts ON sec_sig_metrics(timestamp);
CREATE INDEX IF NOT EXISTS idx_sig_ts    ON signal_metrics(timestamp);
CREATE INDEX IF NOT EXISTS idx_sig_auth  ON signal_metrics(auth_status);
CREATE INDEX IF NOT EXISTS idx_evt_ts    ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_evt_type  ON events(event_type);
"""


class Storage:
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def insert_gnss_sample(self, pvt: dict) -> int:
        sql = """INSERT INTO gnss_samples
            (timestamp, fix_type, num_sv, lat, lon, alt_m, h_acc_m, v_acc_m, pdop, spoof_det_state)
            VALUES (:timestamp, :fix_type, :num_sv, :lat, :lon, :alt_m, :h_acc_m, :v_acc_m, :pdop, :spoof_det_state)"""
        with self._conn() as conn:
            cur = conn.execute(sql, pvt)
            return cur.lastrowid

    def insert_satellite_metrics(self, sample_id: int, satellites: list[dict]) -> None:
        sql = """INSERT INTO satellite_metrics
            (sample_id, timestamp, gnss_id, sv_id, cn0_dbhz, elev_deg, azim_deg, quality_ind)
            VALUES (:sample_id, :timestamp, :gnss_id, :sv_id, :cn0_dbhz, :elev_deg, :azim_deg, :quality_ind)"""
        rows = [{"sample_id": sample_id, **sv} for sv in satellites]
        with self._conn() as conn:
            conn.executemany(sql, rows)

    def insert_sec_sig_metrics(self, sample_id: int, sec_sig: dict) -> None:
        sql = """INSERT INTO sec_sig_metrics
            (sample_id, timestamp, jamming_state, spoofing_state, jam_det_enabled, spf_det_enabled, frequencies_json)
            VALUES (:sample_id, :timestamp, :jamming_state, :spoofing_state, :jam_det_enabled, :spf_det_enabled, :frequencies_json)"""
        row = {
            "sample_id": sample_id,
            "timestamp": sec_sig["timestamp"],
            "jamming_state": sec_sig["jamming_state"],
            "spoofing_state": sec_sig["spoofing_state"],
            "jam_det_enabled": sec_sig["jam_det_enabled"],
            "spf_det_enabled": sec_sig["spf_det_enabled"],
            "frequencies_json": json.dumps(sec_sig.get("frequencies", [])),
        }
        with self._conn() as conn:
            conn.execute(sql, row)

    def insert_signal_metrics(self, sample_id: int, signals: list[dict]) -> None:
        sql = """INSERT INTO signal_metrics
            (sample_id, timestamp, gnss_id, sv_id, sig_id, cno_dbhz, quality_ind, health, pr_used, auth_status)
            VALUES (:sample_id, :timestamp, :gnss_id, :sv_id, :sig_id, :cno_dbhz, :quality_ind, :health, :pr_used, :auth_status)"""
        rows = [{"sample_id": sample_id, **s} for s in signals]
        with self._conn() as conn:
            conn.executemany(sql, rows)

    def insert_rf_metrics(self, rf: dict) -> None:
        sql = """INSERT INTO rf_metrics
            (timestamp, block_id, jamming_state, agc_cnt, noise_per_ms, jamming_indicator, ant_status, ant_power)
            VALUES (:timestamp, :block_id, :jamming_state, :agc_cnt, :noise_per_ms, :jamming_indicator, :ant_status, :ant_power)"""
        with self._conn() as conn:
            conn.execute(sql, rf)

    def insert_event(self, event: dict) -> int:
        sql = """INSERT INTO events (timestamp, event_type, severity, attribution, details, metric_values)
            VALUES (:timestamp, :event_type, :severity, :attribution, :details, :metric_values)"""
        row = {**event, "metric_values": json.dumps(event.get("metric_values", {}))}
        with self._conn() as conn:
            cur = conn.execute(sql, row)
            return cur.lastrowid

    def save_baseline(self, rows: list[dict]) -> None:
        sql = """INSERT INTO baseline_stats
            (computed_at, duration_hours, sample_count, metric, mean, stddev, min_val, max_val)
            VALUES (:computed_at, :duration_hours, :sample_count, :metric, :mean, :stddev, :min_val, :max_val)"""
        with self._conn() as conn:
            conn.executemany(sql, rows)

    def get_latest_baseline(self) -> list[sqlite3.Row]:
        sql = """SELECT * FROM baseline_stats
            WHERE computed_at = (SELECT MAX(computed_at) FROM baseline_stats)"""
        with self._conn() as conn:
            return conn.execute(sql).fetchall()

    def get_events(self, limit: int = 100, event_type: str | None = None) -> list[sqlite3.Row]:
        if event_type:
            sql = "SELECT * FROM events WHERE event_type = ? ORDER BY timestamp DESC LIMIT ?"
            params: tuple = (event_type, limit)
        else:
            sql = "SELECT * FROM events ORDER BY timestamp DESC LIMIT ?"
            params = (limit,)
        with self._conn() as conn:
            return conn.execute(sql, params).fetchall()

    def get_time_series(self, hours: float) -> dict[str, list]:
        cutoff = f"-{hours} hours"
        with self._conn() as conn:
            gnss = [dict(r) for r in conn.execute(
                "SELECT timestamp, num_sv, h_acc_m, pdop FROM gnss_samples WHERE timestamp >= datetime('now', ?) ORDER BY timestamp",
                (cutoff,)).fetchall()]
            rf = [dict(r) for r in conn.execute(
                "SELECT timestamp, block_id, agc_cnt, noise_per_ms, jamming_state, jamming_indicator FROM rf_metrics WHERE timestamp >= datetime('now', ?) ORDER BY timestamp",
                (cutoff,)).fetchall()]
            sats = [dict(r) for r in conn.execute(
                "SELECT timestamp, gnss_id, cn0_dbhz FROM satellite_metrics WHERE timestamp >= datetime('now', ?) AND cn0_dbhz > 0 ORDER BY timestamp",
                (cutoff,)).fetchall()]
        return {"gnss": gnss, "rf": rf, "satellites": sats}

    def get_baseline_window_data(self, hours: float) -> dict[str, list]:
        return self.get_time_series(hours)

    def purge_old_data(self, retain_days: int) -> None:
        cutoff = f"-{retain_days} days"
        with self._conn() as conn:
            for table in ("gnss_samples", "satellite_metrics", "rf_metrics"):
                conn.execute(f"DELETE FROM {table} WHERE timestamp < datetime('now', ?)", (cutoff,))
        logger.info("Purged data older than %d days", retain_days)
