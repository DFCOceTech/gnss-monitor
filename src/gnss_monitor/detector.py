from __future__ import annotations

import logging
import statistics
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .baseline import BaselineManager
    from .config import DetectionConfig
    from .storage import Storage

logger = logging.getLogger(__name__)

FIX_TYPES = {0: "No Fix", 1: "DR Only", 2: "2D Fix", 3: "3D Fix", 4: "GNSS+DR", 5: "Time Fix"}
JAMMING_STATES = {0: "Unknown", 1: "OK", 2: "Warning", 3: "Critical"}
SPOOF_STATES = {0: "Unknown", 1: "No Spoofing", 2: "Spoofing", 3: "Multi-Location"}
BAND_NAMES = {0: "L1", 1: "L2/L5", 2: "E5a", 3: "B1I"}


class _AlertTracker:
    def __init__(self):
        self._open: dict[str, int] = {}

    def is_active(self, key: str) -> bool:
        return key in self._open

    def open(self, key: str, event_id: int) -> None:
        self._open[key] = event_id

    def close(self, key: str) -> None:
        self._open.pop(key, None)

    def active_ids(self) -> set[int]:
        return set(self._open.values())


class AnomalyDetector:
    def __init__(self, storage: Storage, baseline: BaselineManager, cfg: DetectionConfig):
        self.storage = storage
        self.baseline = baseline
        self.cfg = cfg
        self._tracker = _AlertTracker()
        self._active_events: list[dict] = []

    @property
    def active_events(self) -> list[dict]:
        return self._active_events

    def process(self, sample: dict) -> None:
        pvt = sample.get("pvt", {})
        satellites = sample.get("satellites", [])
        rf = sample.get("rf", [])
        ts = pvt.get("timestamp", "")

        self._check_jamming(rf, ts)
        self._check_spoofing(pvt, ts)

        if self.baseline.established:
            self._check_statistical(pvt, satellites, rf, ts)

        self._refresh_active_events()

    # ── Threshold checks ────────────────────────────────────────────────────

    def _check_jamming(self, rf: list[dict], ts: str) -> None:
        warn = self.cfg.threshold.jamming_state_warn
        jam_ind_warn = self.cfg.threshold.jam_indicator_warn

        for band in rf:
            bid = band.get("block_id", 0)
            key = f"jamming_hw_band{bid}"
            jam_state = band.get("jamming_state", 0)
            jam_ind = band.get("jamming_indicator", 0)
            band_name = BAND_NAMES.get(bid, f"Band {bid}")
            is_active = jam_state >= warn or jam_ind >= jam_ind_warn

            if is_active and not self._tracker.is_active(key):
                sev = "critical" if jam_state >= 3 else "warning"
                eid = self.storage.insert_event({
                    "timestamp": ts,
                    "event_type": "jamming",
                    "severity": sev,
                    "attribution": f"Hardware jamming indicator — {band_name} band",
                    "details": f"jammingState={jam_state} ({JAMMING_STATES.get(jam_state,'?')}), jamInd={jam_ind}",
                    "metric_values": {"band": band_name, "jamming_state": jam_state, "jam_indicator": jam_ind},
                })
                self._tracker.open(key, eid)
                logger.warning("JAMMING [%s] state=%d ind=%d", band_name, jam_state, jam_ind)

            elif not is_active and self._tracker.is_active(key):
                self._tracker.close(key)
                logger.info("Jamming cleared [%s]", band_name)

    def _check_spoofing(self, pvt: dict, ts: str) -> None:
        warn = self.cfg.threshold.spoof_det_state_warn
        spoof = pvt.get("spoof_det_state", 0)
        key = "spoofing_hw"
        is_active = spoof >= warn

        if is_active and not self._tracker.is_active(key):
            sev = "critical" if spoof >= 3 else "warning"
            eid = self.storage.insert_event({
                "timestamp": ts,
                "event_type": "spoofing",
                "severity": sev,
                "attribution": "Hardware spoofing detection triggered",
                "details": f"spoofDetState={spoof} ({SPOOF_STATES.get(spoof,'?')})",
                "metric_values": {"spoof_det_state": spoof, "fix_type": pvt.get("fix_type"), "num_sv": pvt.get("num_sv")},
            })
            self._tracker.open(key, eid)
            logger.warning("SPOOFING state=%d", spoof)

        elif not is_active and self._tracker.is_active(key):
            self._tracker.close(key)
            logger.info("Spoofing indicator cleared")

    # ── Statistical checks ───────────────────────────────────────────────────

    def _check_statistical(self, pvt: dict, satellites: list[dict], rf: list[dict], ts: str) -> None:
        z_thresh = self.cfg.statistical.zscore_threshold

        # Satellite count drop → possible jamming / antenna
        num_sv = pvt.get("num_sv")
        if num_sv is not None:
            self._stat_check(
                key="stat_sv_drop",
                z=self.baseline.z_score("num_sv", float(num_sv)),
                direction="low",
                threshold=z_thresh,
                ts=ts,
                event_type="signal_degradation",
                attribution=f"Statistical: satellite count drop (numSV={num_sv})",
                details=f"baseline mean={self.baseline.stats.get('num_sv', {}).get('mean', 0):.1f}",
                metric_values={"num_sv": num_sv},
            )

        # C/N0 mean drop → possible jamming
        cn0_vals = [s["cn0_dbhz"] for s in satellites if s.get("cn0_dbhz", 0) > 0]
        if cn0_vals:
            cn0_mean = statistics.mean(cn0_vals)
            cn0_std = statistics.stdev(cn0_vals) if len(cn0_vals) > 1 else 0.0

            self._stat_check(
                key="stat_cn0_drop",
                z=self.baseline.z_score("cn0_mean", cn0_mean),
                direction="low",
                threshold=z_thresh,
                ts=ts,
                event_type="jamming",
                attribution=f"Statistical: C/N0 drop (mean={cn0_mean:.1f} dBHz)",
                details=f"baseline mean={self.baseline.stats.get('cn0_mean', {}).get('mean', 0):.1f} dBHz",
                metric_values={"cn0_mean": round(cn0_mean, 1)},
            )

            # Uniform high C/N0 → possible spoofing (spoofed signals are unnaturally uniform)
            z_rise = self.baseline.z_score("cn0_mean", cn0_mean)
            if z_rise is not None and z_rise > z_thresh:
                bl_std = self.baseline.stats.get("cn0_mean", {}).get("std", 10)
                if cn0_std < bl_std * 0.5:
                    self._stat_check(
                        key="stat_cn0_uniform",
                        z=z_rise,
                        direction="high",
                        threshold=z_thresh,
                        ts=ts,
                        event_type="spoofing",
                        attribution=f"Statistical: Anomalously uniform C/N0 rise (z={z_rise:.1f})",
                        details=f"mean={cn0_mean:.1f} dBHz, std={cn0_std:.1f} (unusually uniform)",
                        metric_values={"cn0_mean": round(cn0_mean, 1), "cn0_std": round(cn0_std, 1)},
                    )

        # AGC spike → possible jamming
        for band in rf:
            bid = band.get("block_id", 0)
            agc = band.get("agc_cnt")
            if agc is not None:
                self._stat_check(
                    key=f"stat_agc_band{bid}",
                    z=self.baseline.z_score(f"rf{bid}_agc_cnt", float(agc)),
                    direction="high",
                    threshold=z_thresh,
                    ts=ts,
                    event_type="jamming",
                    attribution=f"Statistical: AGC spike on {BAND_NAMES.get(bid, f'Band {bid}')}",
                    details=f"agcCnt={agc}, baseline={self.baseline.stats.get(f'rf{bid}_agc_cnt', {}).get('mean', 0):.0f}",
                    metric_values={"agc_cnt": agc, "band_id": bid},
                )

    def _stat_check(
        self,
        key: str,
        z: float | None,
        direction: str,
        threshold: float,
        ts: str,
        event_type: str,
        attribution: str,
        details: str,
        metric_values: dict,
    ) -> None:
        if z is None:
            return
        triggered = (direction == "low" and z < -threshold) or (direction == "high" and z > threshold)

        if triggered and not self._tracker.is_active(key):
            eid = self.storage.insert_event({
                "timestamp": ts,
                "event_type": event_type,
                "severity": "warning",
                "attribution": attribution,
                "details": details,
                "metric_values": {**metric_values, "z_score": round(z, 2)},
            })
            self._tracker.open(key, eid)
            logger.warning("STAT ALERT [%s] z=%.2f", key, z)

        elif not triggered and self._tracker.is_active(key):
            self._tracker.close(key)

    def _refresh_active_events(self) -> None:
        if not self._tracker.active_ids():
            self._active_events = []
            return
        active_ids = self._tracker.active_ids()
        rows = self.storage.get_events(limit=50)
        self._active_events = [
            {
                "id": r["id"],
                "event_type": r["event_type"],
                "severity": r["severity"],
                "attribution": r["attribution"],
                "timestamp": r["timestamp"],
            }
            for r in rows
            if r["id"] in active_ids
        ]
