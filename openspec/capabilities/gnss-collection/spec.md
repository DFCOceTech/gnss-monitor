# GNSS Collection — Specification

> Version: 1.3 | Status: Implemented and E2E verified | Last updated: 2026-05-09

## Purpose

Read UBX binary messages from ZED-X20P at 1 Hz and persist navigation data, per-satellite metrics, and RF quality metrics for use by the baseline and detection subsystems.

## Functional Requirements

### REQ-COL-001: UBX Message Reception
The system SHALL read NAV-PVT, NAV-SAT, NAV-STATUS, MON-RF, SEC-SIG, and NAV-SIG UBX messages from `/dev/ttyACM0` at approximately 1 Hz.

### REQ-COL-002: UBX Message Polling
The system SHALL poll NAV-PVT, NAV-SAT, NAV-STATUS, MON-RF, SEC-SIG, and NAV-SIG by sending raw UBX poll frames each cycle. Auto-output via CFG-MSG/CFG-PRT is NOT used — the ZED-X20P NACKs CFG-PRT on USB. The collection window SHALL be at least 1.1 s per cycle to allow NAV-PVT responses that are deferred to the next 1 Hz navigation epoch. The input buffer SHALL NOT be reset before polling — the device also auto-outputs NAV-SAT and NAV-STATUS and resetting would discard them.

### REQ-COL-003: NAV-PVT Parsing
The system SHALL extract: fix_type, numSV, lat, lon, height, hAcc, vAcc, pDOP, spoofDetState.

### REQ-COL-004: NAV-SAT Parsing
The system SHALL extract per-satellite: gnssId, svId, C/N0 (cno), elevation, azimuth, qualityInd.

### REQ-COL-005: MON-RF Parsing
The system SHALL extract per RF band: blockId, jammingState, agcCnt, noisePerMS, jamInd, antStatus, antPower. pyubx2 1.3.0 exposes these as direct named attributes (e.g., `jammingState_01`) — they are NOT packed inside a `flags` field.

### REQ-COL-006: Persistent Storage
The system SHALL write every sample to SQLite tables: gnss_samples, satellite_metrics, rf_metrics, sec_sig_metrics, signal_metrics.

### REQ-COL-008: SEC-SIG Parsing
The system SHALL extract from SEC-SIG: overall jammingState, spoofingState, jam/spoof detection enabled flags, and per-frequency jammed status for all reported center frequencies. SEC-SIG spoofingState SHALL override NAV-STATUS spoofDetState as the authoritative spoofing indicator.

### REQ-COL-009: NAV-SIG Parsing
The system SHALL extract from NAV-SIG per-signal: gnssId, svId, sigId, C/N0, qualityInd, health, prUsed, and authStatus. Only signals with qualityInd ≥ 4 (code+carrier locked) SHALL be stored to bound storage growth.

### REQ-COL-007: Resilient Collection
The system SHALL reconnect automatically on serial port failure with 5 s backoff.

## Acceptance Scenarios

### SCENARIO-COL-001: Normal Collection
**GIVEN** ZED-X20P connected at `/dev/ttyACM0` with 3D fix
**WHEN** collector runs for 60 seconds
**THEN** gnss_samples has ≥ 55 rows; satellite_metrics has entries with cn0_dbhz > 0

### SCENARIO-COL-002: Device Reconnect
**GIVEN** collector running, device unplugged then reconnected
**WHEN** 10 seconds elapse after reconnect
**THEN** collector resumes writing samples without process restart

## Implementation Status (2026-05-09)

**Status**: Implemented, deployed, and E2E verified (2026-05-09)

### What's Built
- `src/gnss_monitor/collector.py` — GNSSCollector, 6-message polling mode, `_parse_sec_sig()`, `_parse_nav_sig()`
- `src/gnss_monitor/storage.py` — SQLite insert methods incl. `insert_sec_sig_metrics()`, `insert_signal_metrics()`
- Auto-reconnect loop in `_run()` with 5 s backoff

### Deviations from Spec
- REQ-COL-002 changed from CFG-MSG auto-output to polling — device NACKs CFG-PRT/CFG-MSG on USB
- NAV-STATUS polled alongside NAV-PVT (primary spoofDetState source); falls back to bit-extract from `flags` if `spoofDetState` attribute absent
- Input buffer NOT reset before polling — device auto-outputs NAV-SAT/NAV-STATUS; reset was discarding them
- Collection window is 1.1 s (not 0.5 s) — NAV-PVT response is deferred by device to next 1 Hz nav epoch

### Device Auto-Output Behaviour (confirmed 2026-05-09)
- NAV-SAT: auto-output at ~0.33 Hz (also polled explicitly to guarantee per-cycle delivery)
- NAV-STATUS: auto-output at ~0.33 Hz (also polled explicitly)
- NAV-PVT: NOT auto-output; only responds to explicit polls, deferred to next nav epoch (~0–1 s latency)
- MON-RF: NOT auto-output; only responds to explicit polls (responds quickly, ~10 ms)
- SEC-SIG: NOT auto-output; responds to explicit polls; version=2 on this device
- NAV-SIG: NOT auto-output; responds to explicit polls; 116 signals reported (quality_ind ≥ 4 filter reduces to ~20–40 stored per cycle)

### Confirmed pyubx2 1.3.0 Field Behaviour (on ZED-X20P)
- `lat`, `lon`: pre-scaled floats in degrees — do NOT multiply by 1e-7
- `height`, `hAcc`, `vAcc`: raw integers in mm — multiply by 1e-3 for metres
- `pDOP`: pre-scaled float — do NOT multiply by 0.01
- NAV-SAT repeated groups: `cno_01`…`cno_NN`, `gnssId_01`, `svId_01`, `elev_01`, `azim_01`, `qualityInd_01`
- MON-RF repeated blocks: `jammingState_01`, `agcCnt_01`, `noisePerMS_01`, `jamInd_01`, `blockId_01`, `antStatus_01`, `antPower_01` — all direct named attributes, confirmed on device
