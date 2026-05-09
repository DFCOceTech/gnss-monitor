# Data Sources

## Primary: ZED-X20P via USB CDC ACM

- **Device**: `/dev/ttyACM0`
- **Firmware**: HPG 2.02
- **Hardware**: 000B0000
- **Protocol**: UBX binary (pyubx2 1.3.0)
- **Protocol version**: 50.10 (use `-P 50.10` with ubxtool; earlier sessions used 18.00 which still worked but generates a warning)
- **Supported constellations**: GPS, Galileo, BeiDou, SBAS, QZSS, NAVIC — **GLONASS not supported on this hardware variant**
- **Active constellations**: GPS, Galileo, BeiDou, SBAS (QZSS disabled — not visible at 53.5°N)
- **Connection type**: USB CDC ACM (native USB — baud rate setting is nominal)
- **Configured baud rate**: 115200 (in config.yaml; ignored by USB ACM but required by pyserial)
- **Messages used**:
  | Message | Class | ID | Description |
  |---------|-------|-----|-------------|
  | NAV-PVT | 0x01 | 0x07 | Position/velocity/time + spoofDetState |
  | NAV-SAT | 0x01 | 0x35 | Per-satellite C/N0, elevation, azimuth |
  | NAV-STATUS | 0x01 | 0x03 | Fix status (backup spoofDetState) |
  | MON-RF | 0x0A | 0x38 | Per-band jamming state, AGC, noise |
  | SEC-SIG | 0x27 | 0x09 | Hardware jamming/spoofing state; per-frequency jammed flags (7 freqs) |
  | NAV-SIG | 0x01 | 0x43 | Per-signal C/N0, health, usage, OSNMA authStatus |

## Storage

- **Database**: SQLite 3, WAL mode
- **Path**: `/home/obs-pi-01/gnss-monitor/data/gnss_monitor.db`
- **Retention**: 90 days (configurable via `storage.retain_days`)
- **Tables**: gnss_samples, satellite_metrics, rf_metrics, sec_sig_metrics, signal_metrics, baseline_stats, events

## No External APIs

The system is entirely self-contained and offline-capable.
