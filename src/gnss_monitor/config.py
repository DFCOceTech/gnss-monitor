from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class DeviceConfig:
    port: str = "/dev/ttyACM0"
    baud_rate: int = 115200


@dataclass
class BaselineConfig:
    duration_hours: float = 1.0
    min_samples: int = 100


@dataclass
class ThresholdConfig:
    jamming_state_warn: int = 2
    spoof_det_state_warn: int = 2
    jam_indicator_warn: int = 80
    cn0_drop_db: float = 6.0
    num_sv_min: int = 4


@dataclass
class StatisticalConfig:
    zscore_threshold: float = 3.0
    min_baseline_samples: int = 60


@dataclass
class DetectionConfig:
    threshold: ThresholdConfig = field(default_factory=ThresholdConfig)
    statistical: StatisticalConfig = field(default_factory=StatisticalConfig)


@dataclass
class StorageConfig:
    db_path: str = "/home/obs-pi-01/gnss-monitor/data/gnss_monitor.db"
    retain_days: int = 90


@dataclass
class WebConfig:
    host: str = "0.0.0.0"
    port: int = 5000
    debug: bool = False


@dataclass
class LoggingConfig:
    level: str = "INFO"
    log_file: str = "/home/obs-pi-01/gnss-monitor/logs/gnss_monitor.log"


@dataclass
class Config:
    device: DeviceConfig = field(default_factory=DeviceConfig)
    baseline: BaselineConfig = field(default_factory=BaselineConfig)
    detection: DetectionConfig = field(default_factory=DetectionConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    web: WebConfig = field(default_factory=WebConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


def load_config(path: str | Path | None = None) -> Config:
    cfg = Config()

    search = [path] if path else [
        Path(__file__).parent.parent.parent / "config.yaml",
        Path("/home/obs-pi-01/gnss-monitor/config.yaml"),
    ]

    for p in search:
        if p and Path(p).exists():
            with open(p) as f:
                data = yaml.safe_load(f) or {}
            if data.get("device"):
                cfg.device = DeviceConfig(**data["device"])
            if data.get("baseline"):
                cfg.baseline = BaselineConfig(**data["baseline"])
            if data.get("detection"):
                d = data["detection"]
                cfg.detection = DetectionConfig(
                    threshold=ThresholdConfig(**d.get("threshold", {})),
                    statistical=StatisticalConfig(**d.get("statistical", {})),
                )
            if data.get("storage"):
                cfg.storage = StorageConfig(**data["storage"])
            if data.get("web"):
                cfg.web = WebConfig(**data["web"])
            if data.get("logging"):
                cfg.logging = LoggingConfig(**data["logging"])
            break

    return cfg
