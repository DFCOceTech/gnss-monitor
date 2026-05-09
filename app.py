from __future__ import annotations

import json
import logging
import os
import threading
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, render_template, request
from flask_socketio import SocketIO

from src.gnss_monitor.baseline import BaselineManager
from src.gnss_monitor.collector import GNSSCollector
from src.gnss_monitor.config import load_config
from src.gnss_monitor.detector import (
    AUTH_STATES,
    BAND_NAMES,
    FIX_TYPES,
    FREQ_NAMES,
    JAMMING_STATES,
    SPOOF_STATES,
    AnomalyDetector,
)
from src.gnss_monitor.storage import Storage

cfg = load_config()

Path(cfg.logging.log_file).parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=getattr(logging, cfg.logging.level, logging.INFO),
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(cfg.logging.log_file, mode="a"),
    ],
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("GNSS_SECRET_KEY", "change-me-in-production")
socketio = SocketIO(app, async_mode="threading", cors_allowed_origins="*")

storage = Storage(cfg.storage.db_path)
baseline = BaselineManager(storage, cfg.baseline.duration_hours, cfg.baseline.min_samples)
detector = AnomalyDetector(storage, baseline, cfg.detection)

HISTORY_LEN = 120  # 2 minutes at 1 Hz
_history_lock = threading.Lock()
_history: dict[str, deque] = {
    "timestamps": deque(maxlen=HISTORY_LEN),
    "cn0_mean": deque(maxlen=HISTORY_LEN),
    "num_sv": deque(maxlen=HISTORY_LEN),
    "agc_band0": deque(maxlen=HISTORY_LEN),
    "agc_band1": deque(maxlen=HISTORY_LEN),
    "noise_band0": deque(maxlen=HISTORY_LEN),
    "jam_ind_band0": deque(maxlen=HISTORY_LEN),
}

_state_lock = threading.Lock()
_state: dict = {"status": "starting", "error": None, "timestamp": None}
_sample_count = 0


def _on_sample(sample: dict) -> None:
    global _sample_count
    pvt = sample.get("pvt", {})
    satellites = sample.get("satellites", [])
    rf = sample.get("rf", [])
    sec_sig = sample.get("sec_sig")
    signals = sample.get("signals", [])
    ts = pvt.get("timestamp") or datetime.now(tz=timezone.utc).isoformat()

    sample_id = storage.insert_gnss_sample(pvt)
    if satellites:
        storage.insert_satellite_metrics(sample_id, satellites)
    for band in rf:
        storage.insert_rf_metrics(band)
    if sec_sig:
        storage.insert_sec_sig_metrics(sample_id, sec_sig)
    if signals:
        storage.insert_signal_metrics(sample_id, signals)

    _sample_count += 1
    # Recompute baseline every 60 samples (~1 min) until established, then every 300
    if not baseline.established and _sample_count % 60 == 0:
        baseline.update()
    elif baseline.established and _sample_count % 300 == 0:
        baseline.update()

    detector.process(sample)

    cn0_vals = [s["cn0_dbhz"] for s in satellites if s.get("cn0_dbhz", 0) > 0]
    cn0_mean = sum(cn0_vals) / len(cn0_vals) if cn0_vals else 0.0

    rf_bands = []
    for band in rf:
        bid = band.get("block_id", 0)
        js = band.get("jamming_state", 0)
        rf_bands.append({
            "block_id": bid,
            "label": BAND_NAMES.get(bid, f"Band {bid}"),
            "jamming_state": js,
            "jamming_state_name": JAMMING_STATES.get(js, "Unknown"),
            "agc_cnt": band.get("agc_cnt", 0),
            "noise_per_ms": band.get("noise_per_ms", 0),
            "jam_indicator": band.get("jamming_indicator", 0),
            "ant_status": band.get("ant_status", 0),
        })

    max_jam = max((b["jamming_state"] for b in rf_bands), default=0)
    spoof = pvt.get("spoof_det_state", 0)
    fix_type = pvt.get("fix_type", 0)
    active_events = detector.active_events

    # SEC-SIG security status panel
    sec_sig_state: dict = {}
    if sec_sig:
        sec_freqs = []
        for f in sec_sig.get("frequencies", []):
            freq_khz = f.get("freq_khz", 0)
            sec_freqs.append({
                "freq_mhz": f.get("freq_mhz"),
                "label": FREQ_NAMES.get(freq_khz, f"{f.get('freq_mhz')} MHz"),
                "jammed": f.get("jammed", 0),
            })
        sec_sig_state = {
            "jamming_state": sec_sig.get("jamming_state", 0),
            "jamming_state_name": JAMMING_STATES.get(sec_sig.get("jamming_state", 0), "Unknown"),
            "spoofing_state": sec_sig.get("spoofing_state", 0),
            "spoofing_state_name": SPOOF_STATES.get(sec_sig.get("spoofing_state", 0), "Unknown"),
            "jam_det_enabled": sec_sig.get("jam_det_enabled", 0),
            "spf_det_enabled": sec_sig.get("spf_det_enabled", 0),
            "frequencies": sec_freqs,
            "any_jammed": any(f.get("jammed") for f in sec_sig.get("frequencies", [])),
        }

    # OSNMA authentication summary (Galileo signals only)
    gal_auth = [s for s in signals if s.get("gnss_id") == 2]
    auth_counts = {0: 0, 1: 0, 2: 0, 3: 0}
    for s in gal_auth:
        auth_counts[s.get("auth_status", 0)] = auth_counts.get(s.get("auth_status", 0), 0) + 1
    osnma_state = {
        "authenticated": auth_counts[1],
        "unauthenticated": auth_counts[2],
        "unknown": auth_counts[0],
        "disabled": auth_counts[3],
        "total_gal_signals": len(gal_auth),
        "status": "unauthenticated" if auth_counts[2] > 0 else
                  "authenticated" if auth_counts[1] > 0 else "unknown",
    }

    # Use SEC-SIG jamming state as authoritative when available
    sec_jam = sec_sig.get("jamming_state", 0) if sec_sig else 0
    effective_jam = max(max_jam, sec_jam)

    if effective_jam >= 3 or spoof >= 2 or any(e["severity"] == "critical" for e in active_events):
        status = "critical"
    elif effective_jam >= 2 or active_events:
        status = "warning"
    elif fix_type < 2:
        status = "no_fix"
    else:
        status = "ok"

    with _history_lock:
        _history["timestamps"].append(ts)
        _history["cn0_mean"].append(round(cn0_mean, 1))
        _history["num_sv"].append(pvt.get("num_sv", 0))
        for band in rf:
            bid = band.get("block_id", 0)
            if bid == 0:
                _history["agc_band0"].append(band.get("agc_cnt", 0))
                _history["noise_band0"].append(band.get("noise_per_ms", 0))
                _history["jam_ind_band0"].append(band.get("jamming_indicator", 0))
            elif bid == 1:
                _history["agc_band1"].append(band.get("agc_cnt", 0))
        hist_snap = {k: list(v) for k, v in _history.items()}

    with _state_lock:
        _state.update({
            "timestamp": ts,
            "status": status,
            "error": None,
            "fix_type": fix_type,
            "fix_type_name": FIX_TYPES.get(fix_type, "Unknown"),
            "num_sv": pvt.get("num_sv", 0),
            "lat": round(pvt.get("lat", 0), 7),
            "lon": round(pvt.get("lon", 0), 7),
            "alt_m": round(pvt.get("alt_m", 0), 1),
            "h_acc_m": round(pvt.get("h_acc_m", 0), 2),
            "spoof_det_state": spoof,
            "spoof_det_name": SPOOF_STATES.get(spoof, "Unknown"),
            "baseline_established": baseline.established,
            "baseline_samples": baseline.sample_count,
            "baseline_hours": baseline.duration_hours,
            "rf_bands": rf_bands,
            "cn0_stats": {
                "mean": round(cn0_mean, 1),
                "min": round(min(cn0_vals), 1) if cn0_vals else 0,
                "max": round(max(cn0_vals), 1) if cn0_vals else 0,
                "count": len(cn0_vals),
            },
            "active_events": active_events,
            "sec_sig": sec_sig_state,
            "osnma": osnma_state,
            "history": hist_snap,
        })


def _on_error(msg: str) -> None:
    with _state_lock:
        _state.update({"status": "error", "error": msg})


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def dashboard():
    return render_template("dashboard.html")


@app.route("/events")
def events_page():
    return render_template("events.html")


@app.route("/api/state")
def api_state():
    with _state_lock:
        return jsonify(dict(_state))


@app.route("/api/events")
def api_events():
    event_type = request.args.get("type")
    limit = min(int(request.args.get("limit", 200)), 1000)
    rows = storage.get_events(limit=limit, event_type=event_type or None)
    events = []
    for row in rows:
        e = dict(row)
        try:
            e["metric_values"] = json.loads(e.get("metric_values") or "{}")
        except Exception:
            e["metric_values"] = {}
        events.append(e)
    return jsonify(events)


@app.route("/api/history")
def api_history():
    hours = float(request.args.get("hours", 1))
    hours = max(0.1, min(24.0, hours))
    data = storage.get_time_series(hours)
    return jsonify(data)


@app.route("/api/baseline/duration", methods=["POST"])
def set_baseline_duration():
    hours = float((request.json or {}).get("hours", 1.0))
    baseline.set_duration_hours(hours)
    baseline.update()
    return jsonify({"ok": True, "hours": baseline.duration_hours, "established": baseline.established})


# ── SocketIO ─────────────────────────────────────────────────────────────────

@socketio.on("connect")
def on_connect():
    with _state_lock:
        socketio.emit("update", dict(_state))


@socketio.on("set_baseline_duration")
def on_set_baseline_duration(data):
    hours = float(data.get("hours", 1.0))
    baseline.set_duration_hours(hours)
    baseline.update()
    socketio.emit("baseline_updated", {"hours": baseline.duration_hours, "established": baseline.established})


def _background_emitter():
    while True:
        socketio.sleep(1)
        with _state_lock:
            snap = dict(_state)
        socketio.emit("update", snap)


# ── Startup ──────────────────────────────────────────────────────────────────

def start_services():
    socketio.start_background_task(_background_emitter)

    collector = GNSSCollector(
        port=cfg.device.port,
        baud_rate=cfg.device.baud_rate,
        on_sample=_on_sample,
        on_error=_on_error,
    )
    collector.start()
    logger.info("GNSS Monitor running — dashboard at http://%s:%d", cfg.web.host, cfg.web.port)


if __name__ == "__main__":
    start_services()
    socketio.run(app, host=cfg.web.host, port=cfg.web.port, debug=cfg.web.debug, allow_unsafe_werkzeug=True)
