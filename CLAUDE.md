# CLAUDE.md — GNSS Monitor

Claude Code follows these instructions when working in this repository.

## Project Summary

GNSS quality monitor running on Raspberry Pi 4 + u-blox ZED-X20P (ANN-MB2 antenna).
Reads UBX binary protocol, detects spoofing and jamming, serves a real-time Flask dashboard.

## Key Invariants

- Never commit credentials, `.env` files, or the SQLite database
- Never commit directly to `main` without user approval
- The Pi runs the code; local repo holds specs, docs, and source
- Deploy via `scripts/deploy.sh` (rsync to Pi, restart systemd service)

## Development Workflow (Spec-Anchored)

1. **Spec First** — Update `openspec/capabilities/*/spec.md` (REQ-* and SCENARIO-*)
2. **Tests** — Reference REQ-*/SCENARIO-* in test comments
3. **Implement** — Code to satisfy spec
4. **E2E Verify** — SSH to Pi, run service, verify dashboard shows correct data
5. **Commit & Deploy** — `scripts/deploy.sh`
6. **Reconcile** — Update spec Implementation Status, `ops/status.md`, `ops/changelog.md`

## Build / Run / Deploy

```bash
# Deploy to Pi
./scripts/deploy.sh

# SSH to Pi and tail logs
ssh obs-pi-01@zenith.local "journalctl -u gnss-monitor -f"

# Restart service
ssh obs-pi-01@zenith.local "sudo systemctl restart gnss-monitor"

# Manual test run (Pi)
ssh obs-pi-01@zenith.local "cd ~/gnss-monitor && python3 app.py"

# Run tests locally (mock serial)
pytest tests/ -v --tb=short
```

## Key Paths

| What | Where |
|------|-------|
| Flask app | `app.py` |
| Config | `config.yaml` |
| UBX collector | `src/gnss_monitor/collector.py` |
| Anomaly detector | `src/gnss_monitor/detector.py` |
| Baseline manager | `src/gnss_monitor/baseline.py` |
| SQLite storage | `src/gnss_monitor/storage.py` |
| Dashboard template | `templates/dashboard.html` |
| Events template | `templates/events.html` |
| Systemd service | `systemd/gnss-monitor.service` |
| Deploy script | `scripts/deploy.sh` |
| Capability specs | `openspec/capabilities/*/spec.md` |
| Architecture | `_bmad/architecture.md` |
| Status | `ops/status.md` |
| Changelog | `ops/changelog.md` |

## Pi Connection

- Host: `zenith.local` (192.168.178.84)
- User: `obs-pi-01`
- Auth: SSH public key (`ssh-add ~/.ssh/id_ed25519` required if agent is empty)
- Device: `/dev/ttyACM0` (ZED-X20P via USB CDC ACM, firmware HPG 2.02, protocol 50.10)
- Constellations: GPS, Galileo, BeiDou, SBAS — GLONASS **not supported** on this hardware variant
- gpsd must be stopped: `sudo systemctl stop gpsd gpsd.socket`

## Architecture Notes

- **Protocol**: UBX binary only (pyubx2); device NACKs CFG-PRT/CFG-MSG on USB — collector uses polling mode (raw UBX poll frames at 1 Hz, not auto-output)
- **Trigger**: NAV-PVT arrival drives 1 Hz heartbeat; SAT and RF data used from most recent parse
- **Detection**: Two layers — hardware threshold (jammingState, spoofDetState) + statistical z-score vs baseline
- **Baseline**: SQLite ring-window over configurable hours, recomputed every 5 min once established
- **Dashboard**: Flask + Flask-SocketIO (threading mode), Plotly.js charts, Bootstrap 5 dark theme
- **Storage**: SQLite WAL mode; gnss_samples, satellite_metrics, rf_metrics, baseline_stats, events
