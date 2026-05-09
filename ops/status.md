# Operational Status

**Updated**: 2026-05-09

## What's Working

- Dashboard live at http://192.168.178.84:5000 — all panels populated
- 3D fix, 24–25 SVs, 1.35 m h_acc at new antenna location
- RF bands displaying (L1, L2/L5, E5a) with AGC, noise, jamming indicator
- SEC-SIG panel: hardware jamming/spoofing state + 7-frequency badge grid (all clear)
- OSNMA panel: Galileo signal auth status (currently "UNKNOWN" — firmware update required)
- C/N₀ mean chart and satellite count chart updating in real time
- Socket.IO push confirmed (browser updates without refresh)
- SQLite: 7 tables writing — gnss_samples, satellite_metrics, rf_metrics, sec_sig_metrics, signal_metrics, baseline_stats, events
- Anomaly detection: MON-RF threshold, SEC-SIG per-frequency, OSNMA auth, statistical z-score all active
- Baseline established at current antenna location

## What's Next

1. **Tune zscore_threshold** — consider raising from 3.0 → 3.5 in `config.yaml` to reduce stat_sv_drop false positives (KI-005)
2. **Firmware update** — update ZED-X20P firmware to a version supporting OSNMA to activate cryptographic Galileo authentication (KI-007)
3. **Fix interactive sudo** — KI-006: add NOPASSWD sudoers rule so service restart doesn't require interactive Pi session

## Known Issues

See `ops/known-issues.md`
