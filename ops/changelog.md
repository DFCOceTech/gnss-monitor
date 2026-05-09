# Changelog

## 2026-05-09 — SEC-SIG, NAV-SIG, and OSNMA Pipeline (Session 2 continued)

**User instruction**: Add SEC-SIG and NAV-SIG; update README and spec-anchor docs.

### Added
- `src/gnss_monitor/collector.py` — `_parse_sec_sig()`, `_parse_nav_sig()`; SEC-SIG (0x27/0x09) and NAV-SIG (0x01/0x43) added to poll list; SEC-SIG spoofingState propagated to `_current_pvt` as authoritative source
- `src/gnss_monitor/storage.py` — `sec_sig_metrics` and `signal_metrics` tables; `insert_sec_sig_metrics()`, `insert_signal_metrics()`
- `src/gnss_monitor/detector.py` — `FREQ_NAMES`, `AUTH_STATES` constants; `_check_osnma()` method; SEC-SIG per-frequency jammed check in `_check_jamming()`; SEC-SIG authoritative spoofing in `_check_spoofing()`
- `app.py` — `sec_sig_state` and `osnma_state` built per sample; both pushed in WebSocket state dict
- `templates/dashboard.html` — SEC-SIG security panel (frequency badge grid); OSNMA authentication status panel

### Investigation findings
- SEC-SIG supported on ZED-X20P HPG 2.02: jammingState, spoofingState, 7 monitored frequencies
- NAV-SIG supported: 116 signals, authStatus field present but all 0 (unknown)
- OSNMA NOT supported in HPG 2.02 — `CFG-OSNMA` unknown; firmware update required (KI-007)
- GLONASS not supported on this hardware variant — `CFG-SIGNAL-GLO_ENA` NACKs on write (confirmed via MON-VER: GPS;GAL;BDS only)
- ZED-X20P protocol version is 50.10, not 18.00

---

## 2026-05-09 — Dashboard Live, Collector Fully Debugged (Session 2 continued)

**User instruction**: Get dashboard working; antenna moved to new location; update docs.

### Changed
- `src/gnss_monitor/collector.py` (final state):
  - Collection window extended from 0.5 s to 1.1 s — NAV-PVT poll response deferred to next 1 Hz nav epoch
  - Removed `reset_input_buffer()` from poll cycle — was discarding auto-output NAV-SAT/NAV-STATUS bytes
  - Explicit polls kept for all 4 messages — auto-output rate (~0.33 Hz) too slow to rely on without polling
  - Previous fixes retained: timed loop (no in_waiting break), `payload=b""` default on `_ubx_frame()`
- `app.py` — Added `allow_unsafe_werkzeug=True`; removed `broadcast=True` from `socketio.emit()`
- `templates/base.html` — Fixed Socket.IO CDN (jsdelivr 404 → cdn.socket.io/4.7.5)

### Operational
- `baseline_stats` table cleared manually (2026-05-09) to reset stale baseline from previous antenna location
- Dashboard confirmed live at http://192.168.178.84:5000 with all panels populated: 3D fix, 24–25 SVs, RF bands, C/N₀ chart, satellites chart, live alerts
- New baseline establishing from current antenna location (needs ~100 samples / ~2 min)

### Device Behaviour Confirmed (2026-05-09)
- NAV-PVT: responds to explicit polls only; deferred to next nav epoch (0–1 s after poll)
- NAV-SAT: auto-output at ~0.33 Hz AND responds to explicit polls
- NAV-STATUS: auto-output at ~0.33 Hz AND responds to explicit polls
- MON-RF: responds to explicit polls only; fast response (~10 ms)

---

## 2026-05-09 — Spec Reconciliation (Session 2)

**User instruction**: Update docs before continuing.

### Changed (docs only)
- `openspec/capabilities/gnss-collection/spec.md` — REQ-COL-002 rewritten (polling mode, no buffer reset, 1.1 s window); REQ-COL-005 corrected; implementation status updated with pyubx2 field behaviour
- `openspec/capabilities/dashboard/spec.md` — Deployment fixes documented
- `openspec/capabilities/anomaly-detection/spec.md` — Baseline stats and false-positive note added
- `ops/known-issues.md` — KI-001, KI-003 resolved; KI-004, KI-005, KI-006 added
- `ops/status.md` — Rewritten for current deployed state
- `_bmad/architecture.md` — Collection loop and ADR-004 updated for polling mode
- `CLAUDE.md` — Architecture notes corrected (polling mode, not CFG-MSG)

---

## 2026-05-07 — Initial Build (Session 1)

### Architecture Change: Polling Mode
ZED-X20P NACKs CFG-PRT on USB — cannot configure auto-output via CFG-MSG. Switched collector from stream mode (UBXReader on open serial) to polling mode: send raw UBX poll frames for each message at 1 Hz, collect response bytes over 0.5 s, parse with UBXReader over BytesIO. REQ-COL-002 updated accordingly.

### Confirmed on Device (ZED-X20P + pyubx2 1.3.0)
- lat/lon pre-scaled to degrees; height/hAcc/vAcc raw mm; pDOP pre-scaled — no manual scaling needed
- NAV-SAT: `cno_01`…`cno_NN` (zero-padded 2-digit suffix) — KI-001 resolved
- MON-RF: `jammingState_01` direct named attribute, not bit-packed in `flags_01` — KI-003 resolved
- 3 RF bands (blockId 0/1/2), 19–25 SVs tracked, 3D fix confirmed

### Operational
- Deployed and running at http://192.168.178.84:5000
- 3000+ gnss_samples in SQLite; baseline from ~600 samples (2026-05-07 sky view)
- 7 anomaly events (mostly stat_sv_drop at zscore_threshold=3.0)
- Antenna relocated 2026-05-09 — new baseline collection required
- KI-004 fix deployed to Pi; service restart pending (user must restart from interactive Pi terminal)

---

## 2026-05-07 — Initial Build (Session 1)

**User instruction**: Build GNSS monitor using build_requirements.md, SSH to Pi, use spec-anchor-py as template.

### Added
- Complete project scaffold: BMAD docs, OpenSpec capabilities, ops docs
- `src/gnss_monitor/config.py` — YAML config with dataclass hierarchy
- `src/gnss_monitor/storage.py` — SQLite WAL storage (5 tables + indexes)
- `src/gnss_monitor/collector.py` — GNSSCollector, pyubx2 UBXReader, CFG-MSG startup config
- `src/gnss_monitor/baseline.py` — BaselineManager, rolling window, z-score API
- `src/gnss_monitor/detector.py` — AnomalyDetector, threshold + statistical, deduplication
- `app.py` — Flask + Flask-SocketIO, background emitter, REST API + WebSocket
- `templates/dashboard.html` — Real-time dashboard, Plotly.js charts, Bootstrap 5 dark
- `templates/events.html` — Historical events, filter, timeline chart, detail modal
- `systemd/gnss-monitor.service` — Systemd unit, conflicts with gpsd
- `scripts/deploy.sh` — rsync to Pi + service restart
- `config.yaml` — Default configuration
- Capability specs for gnss-collection, anomaly-detection, dashboard

### Pi Setup
- Installed: pyubx2 1.3.0, flask-socketio 5.6.1 (user site-packages)
- Device confirmed at `/dev/ttyACM0`
- gpsd confirmed inactive
