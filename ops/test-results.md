# E2E Test Results

## 2026-05-09 — Dashboard E2E Verification

**Verified by**: Human operator (obs-pi-01@zenith.local)
**Service**: gnss-monitor.service (PID 2347)

### Environment
- Pi 4, Python 3.13.5, pyubx2 1.3.0, flask-socketio 5.6.1
- ZED-X20P at /dev/ttyACM0, ANN-MB2 antenna (new location as of 2026-05-09)
- Dashboard at http://192.168.178.84:5000

### SCENARIO-COL-001: Normal Collection
**Result**: PASS
- gnss_samples writing confirmed: count grew from 3479 → 3692+ during session
- fix_type=3 (3D Fix), num_sv=24–25, h_acc_m=1.35–1.37 m across observed samples
- satellite_metrics writing confirmed: C/N₀ panel populated in dashboard
- rf_metrics writing confirmed: RF bands panel populated (3 bands: L1, L2/L5, E5a)

### REQ-DASH-001: Real-Time Dashboard
**Result**: PASS
- Dashboard loads at http://192.168.178.84:5000
- WebSocket push confirmed: all panels update without page refresh
- Status, fix type, satellite count, position accuracy, C/N₀, RF bands all live

### REQ-DASH-002: Current Status Display
**Result**: PASS (with known limitation)
- Fix type: 3D Fix ✓
- Satellite count: 24 ✓
- Position accuracy: 1.35 m ✓
- C/N₀ mean: populated with real values ✓
- RF bands: L1, L2/L5, E5a with AGC/noise/JamInd ✓
- Spoofing state: "Unknown" (jammingState=0, correct — device not flagging)
- Active alerts: stat_agc_band0 warning (false positive from stale baseline; cleared after baseline reestablishment)

### REQ-DASH-003: Time-Series Charts
**Result**: PASS
- C/N₀ mean over time: flat line visible (note: 0 dBHz shown because satellite C/N₀ was not yet populated at capture time; populated after final collector fix)
- Satellites tracked chart: live trace showing 22–26 SVs ✓
- AGC count and jamming indicator charts: visible in lower section ✓

### REQ-DASH-004/005: Events Page
**Result**: Not re-verified this session (events page was confirmed working in earlier debug logs showing stat alerts being written to DB)

### Known Gaps
- Unit tests not yet written (tests/ directory is empty)
- SCENARIO-COL-002 (device reconnect) not formally tested
