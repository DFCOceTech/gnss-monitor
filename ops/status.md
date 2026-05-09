# Operational Status

**Updated**: 2026-05-09

## What's Working

- Dashboard live at http://192.168.178.84:5000 — all panels populated
- 3D fix, 24–25 SVs, 1.35 m h_acc at new antenna location
- RF bands displaying (L1, L2/L5, E5a) with AGC, noise, jamming indicator
- C/N₀ mean chart and satellite count chart updating in real time
- Socket.IO push confirmed (browser updates without refresh)
- SQLite storage writing — ~3700+ samples total
- Anomaly detection active — threshold and statistical checks running
- New baseline establishing from current antenna location (cleared 2026-05-09 after relocation)

## What's Next

1. **Wait for baseline** — ~100 samples (~2 min from last restart) to establish new baseline at current location; false-positive alerts will clear once established
2. **Tune zscore_threshold** — once new baseline stabilises, consider raising from 3.0 → 3.5 in `config.yaml` to reduce stat_sv_drop false positives (KI-005)
3. **Fix interactive sudo** — KI-006: add NOPASSWD sudoers rule so service restart doesn't require interactive Pi session

## Known Issues

See `ops/known-issues.md`
