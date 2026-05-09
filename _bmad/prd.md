# Product Requirements Document — GNSS Monitor

> Version: 1.0 | Status: Active | Last updated: 2026-05-07

## Functional Requirements

| ID | Requirement | OpenSpec Capability |
|----|-------------|---------------------|
| FR-01 | Record GNSS data (position, satellites, RF metrics) at 1 Hz | `gnss-collection` |
| FR-02 | Record baseline of GNSS quality in all bands and constellations | `gnss-collection` |
| FR-03 | Detect changes in signal quality across bands | `anomaly-detection` |
| FR-04 | Attribute changes to multi-path, spoofing, or jamming | `anomaly-detection` |
| FR-05 | Write log of quality metrics, assessments, and attribution | `gnss-collection` |
| FR-06 | Display current status on a real-time dashboard | `dashboard` |
| FR-07 | Dashboard for historical interference/spoofing/jamming event lookup | `dashboard` |

## Non-Functional Requirements

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-01 | Collection latency | ≤ 1 s end-to-end from GPS epoch to dashboard update |
| NFR-02 | Storage retention | 90 days rolling, SQLite WAL |
| NFR-03 | Availability | Systemd-managed, auto-restart on failure |
| NFR-04 | Baseline establishment | 100 samples minimum; default 1 h window, user-configurable |

## Interface Contracts

| Interface | Protocol | Notes |
|-----------|----------|-------|
| ZED-X20P | UBX binary via `/dev/ttyACM0` | NAV-PVT, NAV-SAT, MON-RF at 1 Hz |
| Dashboard | HTTP + WebSocket | Flask-SocketIO; client at port 5000 |
| Configuration | YAML | `config.yaml` in project root |

## Out of Scope

- RF interference (hardware-level)
- AIS spoofing
- ADS-B spoofing
