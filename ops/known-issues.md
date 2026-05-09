# Known Issues

## KI-001: pyubx2 repeated-group attribute naming — RESOLVED
**Status**: Resolved (2026-05-09)
**Description**: pyubx2 1.3.0 repeated-group field names assumed to use zero-padded 2-digit suffix (`_01`, `_02`, …).
**Resolution**: Confirmed on ZED-X20P — all NAV-SAT and MON-RF fields use the `_01`…`_NN` suffix. Direct named attributes confirmed: `cno_01`, `gnssId_01`, `jammingState_01`, `agcCnt_01`, `jamInd_01`, etc.

## KI-002: Packages installed as user site-packages
**Status**: Monitored
**Description**: pip installed pyubx2 and flask-socketio to `~/.local/` (obs-pi-01 home). The systemd service sets `PYTHONPATH` to the versioned path `/home/obs-pi-01/.local/lib/python3.13/site-packages`. If Python version changes, this path must be updated in the service file.
**Mitigation**: After deploy, verify `sudo systemctl status gnss-monitor` shows no ImportError.

## KI-003: MON-RF jammingState field location — RESOLVED
**Status**: Resolved (2026-05-09)
**Description**: Interface description suggested jammingState might be packed in bits 1:0 of `flags` byte rather than exposed as a named attribute.
**Resolution**: Confirmed on ZED-X20P — `jammingState_01` is a direct named attribute in pyubx2 1.3.0. The flags-bit fallback path in collector.py can be removed in a future cleanup.

## KI-004: Serial read loop and NAV-PVT polling — RESOLVED
**Status**: Resolved (2026-05-09)
**Description**: Two related issues: (1) original `in_waiting`-based read loop exited on momentary buffer gaps; (2) NAV-PVT poll response is deferred by the device to the next 1 Hz nav epoch, so a 0.5 s collection window missed it ~80% of cycles. Additionally, `reset_input_buffer()` was discarding auto-output NAV-SAT/NAV-STATUS bytes before collection began.
**Resolution**: Collection window extended to 1.1 s (covers full nav epoch wait); `reset_input_buffer()` removed from poll cycle; explicit polls kept for all 4 messages to guarantee per-cycle delivery regardless of auto-output timing. Dashboard confirmed live with all panels populated.

## KI-005: Statistical false positives at zscore_threshold=3.0
**Status**: Open — baseline reset in progress
**Description**: Old baseline (established at previous antenna location) caused immediate stat_agc_band0 false-positive alerts after antenna relocation. baseline_stats table cleared manually on 2026-05-09 to force reestablishment from new location. With numSV std=0.809 on the old baseline, normal dips to 22–23 SVs also produced spurious `stat_sv_drop` events.
**Mitigation**: Allow new baseline to establish (~100 samples / ~2 min). Once stable, consider raising `detection.statistical.zscore_threshold` in `config.yaml` to 3.5–4.0 to reduce sv_drop false positives.
**Operational note**: To reset baseline after antenna relocation: `DELETE FROM baseline_stats` in the SQLite DB. The service picks up the cleared baseline at next startup.

## KI-007: OSNMA requires firmware update
**Status**: Open
**Description**: ZED-X20P firmware HPG 2.02 does not support Galileo OSNMA. `CFG-OSNMA` config group is unknown to ubxtool, and all NAV-SIG `authStatus` values remain 0 (unknown). The OSNMA detection pipeline and dashboard panel are fully implemented and will activate automatically once the device runs a firmware version that supports OSNMA.
**Resolution**: Update firmware via u-blox u-center (Windows). User intends to do this. After update, re-probe SEC-SIG and NAV-SIG to confirm authStatus values.

## KI-006: systemd service requires interactive sudo for restart
**Status**: Open
**Description**: `sudo systemctl restart gnss-monitor` fails over non-interactive SSH (`sudo: a terminal is required`). The service can only be restarted by the user from an interactive Pi terminal session.
**Mitigation**: Add a NOPASSWD sudoers rule for the specific systemctl command, or use `sudo -S` with password piped in deploy.sh.
