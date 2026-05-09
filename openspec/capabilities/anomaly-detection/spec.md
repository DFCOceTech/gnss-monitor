# Anomaly Detection — Specification

> Version: 1.2 | Status: Implemented | Last updated: 2026-05-09

## Purpose

Detect GNSS signal anomalies (jamming, spoofing, multipath/degradation) using two complementary approaches: hardware threshold checks and statistical deviation from a computed baseline.

## Functional Requirements

### REQ-DET-001: Baseline Establishment
The system SHALL compute a baseline of normal signal characteristics (C/N0 mean, satellite count, AGC, noise) from a configurable rolling time window (default 1 h, minimum 100 samples, maximum 24 h).

### REQ-DET-002: Threshold Jamming Detection
The system SHALL detect jamming when: (a) MON-RF jammingState ≥ configured warn level (default 2) OR jamInd ≥ configured threshold (default 80), per RF band; OR (b) SEC-SIG reports `jammed=1` on any monitored center frequency.

### REQ-DET-003: Threshold Spoofing Detection
The system SHALL detect spoofing when SEC-SIG `spoofingState` ≥ configured warn level (default 2). SEC-SIG is the authoritative spoofing source; NAV-STATUS `spoofDetState` is used as fallback when SEC-SIG is unavailable.

### REQ-DET-009: OSNMA Authentication Detection
The system SHALL detect spoofing when any Galileo signal reports `authStatus=2` (unauthenticated) in NAV-SIG. This event SHALL have severity=critical. When firmware does not support OSNMA, all authStatus values will be 0 (unknown) and no events will fire.

### REQ-DET-004: Statistical Detection
The system SHALL detect anomalies when any monitored metric deviates from baseline by more than `zscore_threshold` standard deviations (default 3.0).

### REQ-DET-005: Monitored Statistical Metrics
Statistical detection SHALL cover: satellite count (drop), C/N0 mean (drop = jamming, uniform rise = spoofing indicator), AGC count per band (spike = jamming).

### REQ-DET-006: Event Deduplication
The system SHALL create at most one open event per anomaly type/band; subsequent samples during the same anomaly SHALL NOT create duplicate events.

### REQ-DET-007: Event Attribution
Each event SHALL carry: event_type, severity (warning/critical), attribution text, and metric values at time of detection.

### REQ-DET-008: Baseline User Control
The user SHALL be able to set the baseline duration via the dashboard (0.25–24 h range).

## Acceptance Scenarios

### SCENARIO-DET-001: Hardware Jamming
**GIVEN** baseline established, MON-RF jammingState rises to 2 on band 0
**WHEN** next sample processed
**THEN** one event of type 'jamming' with severity 'warning' is created; no duplicate on next sample

### SCENARIO-DET-002: Statistical C/N0 Drop
**GIVEN** baseline established with cn0_mean=38.0 std=2.0
**WHEN** current cn0_mean drops to 28.0 (z=-5.0, below threshold of 3.0)
**THEN** event of type 'jamming' created with z_score in metric_values

### SCENARIO-DET-003: Baseline Not Ready
**GIVEN** fewer than min_samples collected
**WHEN** sample processed
**THEN** statistical checks skipped; hardware threshold checks still run

## Implementation Status (2026-05-09)

**Status**: Implemented and deployed

### What's Built
- `src/gnss_monitor/detector.py` — AnomalyDetector with _AlertTracker for deduplication
- `src/gnss_monitor/baseline.py` — BaselineManager with rolling window from SQLite
- Threshold checks: `_check_jamming()` (MON-RF + SEC-SIG per-frequency), `_check_spoofing()` (SEC-SIG authoritative), `_check_osnma()` (NAV-SIG authStatus)
- Statistical checks: `_check_statistical()` covering num_sv, cn0_mean, AGC per band
- Uniform C/N0 rise spoofing heuristic (statistical)
- `FREQ_NAMES` dict mapping SEC-SIG center frequencies (kHz) to human-readable band labels

### Observed Behaviour (baseline from ~600 samples, 2026-05-07)
- numSV baseline: mean=24.30, std=0.809
- h_acc_m baseline: mean=0.83 m, std=0.019 m
- pdop baseline: mean=0.99, std=0.021
- cn0_mean baseline: mean=37.01 dBHz, std=1.346 dBHz
- At zscore_threshold=3.0, normal dips to 22 SVs trigger stat_sv_drop events (false positives)
- Consider raising zscore_threshold to 3.5–4.0 once more baseline data is collected
