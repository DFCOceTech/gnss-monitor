# Architecture — GNSS Monitor

> Version: 1.3 | Status: Active | Last updated: 2026-05-09
> **Last Reconciled: 2026-05-09**

## System Context

```
[ZED-X20P via USB]
        |  UBX binary /dev/ttyACM0
        ↓
[GNSSCollector thread]  ── pyubx2 UBXReader ──→  NAV-PVT / NAV-SAT / NAV-STATUS
        |                                          MON-RF / SEC-SIG / NAV-SIG
        | on_sample() callback (~0.9 Hz)
        ↓
[app.py main process]
    ├── Storage (SQLite WAL)
    │      ├── gnss_samples (1 Hz)
    │      ├── satellite_metrics (per SV, from NAV-SAT)
    │      ├── rf_metrics (per band, from MON-RF)
    │      ├── sec_sig_metrics (per sample, from SEC-SIG)
    │      ├── signal_metrics (per locked signal, from NAV-SIG)
    │      ├── baseline_stats (computed)
    │      └── events (alerts)
    │
    ├── BaselineManager
    │      └── Computes mean/std over rolling time window
    │          Recomputed every 60 s until established, then every 5 min
    │
    ├── AnomalyDetector
    │      ├── Threshold checks — MON-RF (jammingState, jamInd per band)
    │      ├── Threshold checks — SEC-SIG (jammingState, spoofingState, per-freq jammed)
    │      ├── OSNMA check — NAV-SIG authStatus=2 on any Galileo signal → critical
    │      └── Statistical checks (z-score vs baseline: num_sv, C/N0, AGC)
    │
    └── Flask + Flask-SocketIO (threading mode)
           ├── GET /               → dashboard.html
           ├── GET /events         → events.html
           ├── GET /api/state      → current state JSON
           ├── GET /api/events     → event history JSON
           ├── GET /api/history    → time-series from DB
           ├── POST /api/baseline/duration → update baseline window
           └── WS  emit 'update'   → push state to browser every 1 s
```

## Key Data Flows

### Collection Loop (~0.9 Hz)
The ZED-X20P NACKs CFG-PRT/CFG-MSG on USB. Collector uses **polling mode** with a key constraint: NAV-PVT poll responses are deferred by the device to the next 1 Hz navigation epoch (0–1 s latency). The device also auto-outputs NAV-SAT and NAV-STATUS at ~0.33 Hz independently.
1. Send raw UBX poll frames for NAV-PVT, NAV-SAT, NAV-STATUS, MON-RF, SEC-SIG, NAV-SIG (20 ms apart) — **do NOT reset input buffer** first, to preserve any auto-output bytes already queued
2. Accumulate all bytes for **1.1 s** — covers the full nav epoch wait for NAV-PVT, plus captures auto-output NAV-SAT/NAV-STATUS if they arrive mid-window
3. Feed raw bytes into `UBXReader(BytesIO(raw), protfilter=2)` — skips NMEA, finds UBX frames
4. NAV-PVT → `_parse_pvt()` → updates `_current_pvt`
5. NAV-SAT → `_parse_sat()` → updates `_current_sat`
6. MON-RF → `_parse_rf()` → updates `_current_rf`
7. NAV-STATUS → extracts `spoofDetState`, patches into `_current_pvt`
8. SEC-SIG → `_parse_sec_sig()` → updates `_current_sec_sig`; `spoofingState` overrides `_current_pvt["spoof_det_state"]`
9. NAV-SIG → `_parse_nav_sig()` → updates `_current_signals` (qualityInd ≥ 4 only)
10. If `_current_pvt` is set: `_emit()` bundles pvt + sat + rf + sec_sig + signals → calls `on_sample()`

### Sample Processing
1. Write to SQLite (gnss_samples, satellite_metrics, rf_metrics, sec_sig_metrics, signal_metrics)
2. Baseline recomputation check
3. AnomalyDetector.process() → threshold + SEC-SIG + OSNMA + statistical checks → insert events
4. Build `sec_sig_state` and `osnma_state` summary dicts for dashboard
5. Update in-memory state dict (includes `sec_sig`, `osnma` keys) + history ring buffer (120 samples)

### Dashboard Push
- `_background_emitter` task runs every 1 s via socketio.sleep()
- Copies state dict under lock → emits `'update'` broadcast to all clients
- Client `socket.on('update')` updates DOM + Plotly traces in-place

## Execution Environment

- **Hardware**: Raspberry Pi 4, 4 GB RAM, Raspberry Pi OS (Debian Bookworm)
- **Python**: 3.13.5 (system)
- **Key packages**: pyubx2 1.3.0, flask-socketio 5.6.1, flask 3.1.1, pyserial 3.5
- **Device firmware**: HPG 2.02, protocol version 50.10 (use `-P 50.10` with ubxtool)
- **Supported constellations**: GPS, Galileo, BeiDou, SBAS, QZSS, NAVIC — GLONASS not supported on this hardware variant
- **Installed**: globally via pip (user site-packages at `~/.local/`)
- **Service**: systemd unit `gnss-monitor.service`, runs as `obs-pi-01`

## Architectural Decision Records

### ADR-001: UBX Binary Protocol (not NMEA/gpsd)
- **Status**: Accepted
- **Context**: ZED-X20P supports both NMEA and UBX. MON-RF (jamming metrics) and fine-grained spoofing state are UBX-only.
- **Decision**: Read UBX directly from `/dev/ttyACM0` via pyubx2; gpsd disabled.
- **Consequences**: Full access to MON-RF, NAV-STATUS spoofDetState; no gpsd dependency.

### ADR-002: SQLite over InfluxDB
- **Status**: Accepted
- **Context**: Need time-series storage queryable for both current status and historical analysis.
- **Decision**: SQLite with WAL mode and indexed timestamp columns. 90-day rolling retention.
- **Consequences**: Simple, zero-config, queryable with standard SQL. Not horizontally scalable (not needed).

### ADR-003: Flask-SocketIO Threading Mode
- **Status**: Accepted
- **Context**: eventlet/gevent not installed; simple-websocket backend available.
- **Decision**: `async_mode='threading'` with standard Python threads.
- **Consequences**: Simple, no monkey-patching. Sufficient for ≤ 10 concurrent dashboard clients.

### ADR-004: Polling-per-tick, emit-after-parse
- **Status**: Accepted (revised from original stream-mode design)
- **Context**: ZED-X20P NACKs CFG-PRT on USB — auto-output cannot be enabled. Original design assumed stream-mode UBXReader on open serial; this was replaced in session 2.
- **Decision**: Each cycle polls all six messages (NAV-PVT, NAV-SAT, NAV-STATUS, MON-RF, SEC-SIG, NAV-SIG) explicitly without resetting the input buffer, collects all bytes for 1.1 s (covers NAV-PVT epoch latency), then emits one sample with all data bundled.
- **Consequences**: All six message types are always fresh per cycle. Auto-output bytes (NAV-SAT, NAV-STATUS at ~0.33 Hz) are also captured. Cycle runs at ~0.9 Hz due to 1.1 s window dominating.
