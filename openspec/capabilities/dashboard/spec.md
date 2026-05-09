# Dashboard — Specification

> Version: 1.2 | Status: Implemented and E2E verified | Last updated: 2026-05-09

## Purpose

Provide a web-based interface with (1) a real-time status dashboard pushed via WebSocket at 1 Hz, and (2) a historical events view for investigating past anomalies.

## Functional Requirements

### REQ-DASH-001: Real-Time Dashboard
The system SHALL serve a dashboard at `/` that updates via WebSocket push at ≤ 2 s interval.

### REQ-DASH-002: Current Status Display
The dashboard SHALL show: overall status (OK/Warning/Critical/No Fix), fix type, satellite count, position, horizontal accuracy, C/N0 statistics, per-band RF metrics (jamming state, AGC, noise, jam indicator), spoofing detection state, and active alerts.

### REQ-DASH-003: Time-Series Charts
The dashboard SHALL display rolling 2-minute charts for: C/N0 mean, satellite count, L1 AGC count, L1 jamming indicator.

### REQ-DASH-004: Historical Events Page
The system SHALL serve an events page at `/events` listing past events with filtering by type and configurable limit.

### REQ-DASH-005: Event Detail
Each event in the history view SHALL be expandable to show: timestamp, type, severity, attribution, details, and metric values at time of detection.

### REQ-DASH-006: Baseline Control
The dashboard SHALL allow the user to set the baseline duration (0.25–24 h) and display baseline status (collecting / established + sample count).

### REQ-DASH-007: SEC-SIG Security Panel
The dashboard SHALL display a security panel showing: SEC-SIG overall jammingState and spoofingState, and a frequency badge grid for all monitored center frequencies indicating jammed/clear status per frequency.

### REQ-DASH-008: OSNMA Authentication Panel
The dashboard SHALL display a Galileo OSNMA authentication panel showing counts of authenticated, unauthenticated, and unknown signals. When firmware does not support OSNMA, the panel SHALL indicate "Firmware update required" rather than showing zero counts as a failure.

## Implementation Status (2026-05-09)

**Status**: Implemented and E2E verified (2026-05-09)

### What's Built
- `app.py` — Flask routes + Flask-SocketIO; background emitter at 1 Hz; `sec_sig` and `osnma` state fields
- `templates/dashboard.html` — Bootstrap 5 dark, Plotly.js, Socket.IO client; SEC-SIG and OSNMA panels
- `templates/events.html` — Table + timeline chart, detail modal
- `/api/state`, `/api/events`, `/api/history`, `/api/baseline/duration` REST endpoints

### Fixes Applied During Deployment
- `allow_unsafe_werkzeug=True` added to `socketio.run()` (required by flask-socketio 5.6.1 with Werkzeug dev server)
- `broadcast=True` removed from `socketio.emit()` (removed in flask-socketio 5.x)
- Socket.IO client CDN changed from `cdn.jsdelivr.net/npm/socket.io@4.7.5` (404) to `cdn.socket.io/4.7.5` (official CDN)
