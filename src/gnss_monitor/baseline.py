from __future__ import annotations

import logging
import statistics
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .storage import Storage

logger = logging.getLogger(__name__)


class BaselineManager:
    def __init__(self, storage: Storage, duration_hours: float, min_samples: int):
        self.storage = storage
        self.duration_hours = duration_hours
        self.min_samples = min_samples

        self._stats: dict[str, dict] = {}
        self._established = False
        self._computed_at: str | None = None
        self._sample_count: int = 0

        self._load_from_db()

    @property
    def established(self) -> bool:
        return self._established

    @property
    def stats(self) -> dict[str, dict]:
        return self._stats

    @property
    def sample_count(self) -> int:
        return self._sample_count

    def _load_from_db(self) -> None:
        rows = self.storage.get_latest_baseline()
        if not rows:
            return
        for row in rows:
            self._stats[row["metric"]] = {
                "mean": row["mean"],
                "std": max(row["stddev"], 0.001),
                "min": row["min_val"],
                "max": row["max_val"],
            }
        if self._stats:
            self._established = True
            self._computed_at = rows[0]["computed_at"]
            self._sample_count = rows[0]["sample_count"]
            logger.info("Loaded baseline from DB (%d metrics)", len(self._stats))

    def update(self) -> bool:
        data = self.storage.get_baseline_window_data(self.duration_hours)
        gnss_rows = data["gnss"]
        rf_rows = data["rf"]
        sat_rows = data["satellites"]

        if len(gnss_rows) < self.min_samples:
            logger.debug("Baseline: %d/%d samples collected", len(gnss_rows), self.min_samples)
            return False

        buckets: dict[str, list[float]] = {
            "num_sv": [],
            "h_acc_m": [],
            "pdop": [],
        }

        for row in gnss_rows:
            for key in ("num_sv", "h_acc_m", "pdop"):
                v = row.get(key)
                if v is not None:
                    buckets[key].append(float(v))

        # Per-band RF metrics
        for row in rf_rows:
            bid = row.get("block_id", 0)
            for key in ("agc_cnt", "noise_per_ms", "jamming_indicator"):
                v = row.get(key)
                if v is not None:
                    mkey = f"rf{bid}_{key}"
                    buckets.setdefault(mkey, []).append(float(v))

        # Mean C/N0 per sample epoch (group satellite rows by timestamp)
        ts_cn0: dict[str, list[float]] = {}
        for row in sat_rows:
            ts = row.get("timestamp", "")
            cn0 = row.get("cn0_dbhz")
            if ts and cn0 and float(cn0) > 0:
                ts_cn0.setdefault(ts, []).append(float(cn0))

        if ts_cn0:
            buckets["cn0_mean"] = [statistics.mean(vals) for vals in ts_cn0.values()]

        new_stats: dict[str, dict] = {}
        for metric, values in buckets.items():
            if len(values) < 2:
                continue
            mean = statistics.mean(values)
            std = statistics.stdev(values) if len(values) > 1 else 0.0
            new_stats[metric] = {
                "mean": mean,
                "std": max(std, 0.001),
                "min": min(values),
                "max": max(values),
            }

        if not new_stats:
            return False

        now = datetime.now(tz=timezone.utc).isoformat()
        db_rows = [
            {
                "computed_at": now,
                "duration_hours": self.duration_hours,
                "sample_count": len(gnss_rows),
                "metric": metric,
                "mean": s["mean"],
                "stddev": s["std"],
                "min_val": s["min"],
                "max_val": s["max"],
            }
            for metric, s in new_stats.items()
        ]
        self.storage.save_baseline(db_rows)

        self._stats = new_stats
        self._established = True
        self._computed_at = now
        self._sample_count = len(gnss_rows)
        logger.info("Baseline updated: %d samples, %d metrics", len(gnss_rows), len(new_stats))
        return True

    def z_score(self, metric: str, value: float) -> float | None:
        stat = self._stats.get(metric)
        if stat is None or stat["std"] < 0.001:
            return None
        return (value - stat["mean"]) / stat["std"]

    def set_duration_hours(self, hours: float) -> None:
        self.duration_hours = max(0.25, min(24.0, hours))
        self._established = False
        self._stats = {}
        logger.info("Baseline window set to %.2f hours", self.duration_hours)
