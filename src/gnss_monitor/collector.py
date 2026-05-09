from __future__ import annotations

import logging
import struct
import threading
import time
from datetime import datetime, timezone
from typing import Callable

import serial
from pyubx2 import UBXReader

logger = logging.getLogger(__name__)

GNSS_NAMES = {0: "GPS", 1: "SBAS", 2: "Galileo", 3: "BeiDou", 4: "IMES", 5: "QZSS", 6: "GLONASS"}

# UBX messages to poll each cycle
_POLL_MSGS: list[tuple[int, int]] = [
    (0x01, 0x07),  # NAV-PVT
    (0x01, 0x35),  # NAV-SAT
    (0x01, 0x03),  # NAV-STATUS
    (0x0A, 0x38),  # MON-RF
]


def _ubx_frame(cls: int, msg_id: int, payload: bytes = b"") -> bytes:
    """Build a raw UBX frame with checksum."""
    header = struct.pack("<BBBBH", 0xB5, 0x62, cls, msg_id, len(payload))
    body = header[2:] + payload
    ck_a = ck_b = 0
    for b in body:
        ck_a = (ck_a + b) & 0xFF
        ck_b = (ck_b + ck_a) & 0xFF
    return header + payload + bytes([ck_a, ck_b])


def _cfg_msg_frame(msg_class: int, msg_id: int, rate_usb: int = 1) -> bytes:
    """CFG-MSG: set per-port output rate (I2C/UART1/UART2/USB/SPI/res)."""
    payload = struct.pack("BBBBBBBB", msg_class, msg_id, 0, 0, 0, rate_usb, 0, 0)
    return _ubx_frame(0x06, 0x01, payload)


class GNSSCollector:
    def __init__(
        self,
        port: str,
        baud_rate: int,
        on_sample: Callable[[dict], None],
        on_error: Callable[[str], None] | None = None,
    ):
        self.port = port
        self.baud_rate = baud_rate
        self.on_sample = on_sample
        self.on_error = on_error
        self._running = False
        self._thread: threading.Thread | None = None

        self._current_pvt: dict | None = None
        self._current_sat: list[dict] = []
        self._current_rf: list[dict] = []

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="gnss-collector")
        self._thread.start()
        logger.info("GNSS collector started on %s", self.port)

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _configure(self, ser: serial.Serial) -> None:
        # Device NACKs CFG-PRT on USB; we use polling mode instead.
        # Verify UBX comms by polling NAV-PVT once.
        ser.reset_input_buffer()
        ser.write(_ubx_frame(0x01, 0x07))
        time.sleep(0.2)
        probe = ser.read(256)
        if b"\xb5\x62" in probe:
            logger.info("UBX comms confirmed (NAV-PVT poll succeeded)")
        else:
            logger.warning("No UBX response to NAV-PVT poll — device may need reset")

    def _parse_pvt(self, msg) -> dict:
        ts = datetime.now(tz=timezone.utc).isoformat()
        # pyubx2 pre-scales lat/lon to degrees and pDOP to its unit.
        # height/hAcc/vAcc are raw integers in mm.
        # spoofDetState lives in NAV-STATUS (updated via NAV-STATUS path).
        return {
            "timestamp": ts,
            "fix_type": int(getattr(msg, "fixType", 0) or 0),
            "num_sv": int(getattr(msg, "numSV", 0) or 0),
            "lat": float(getattr(msg, "lat", 0.0) or 0.0),
            "lon": float(getattr(msg, "lon", 0.0) or 0.0),
            "alt_m": float(getattr(msg, "height", 0) or 0) * 1e-3,
            "h_acc_m": float(getattr(msg, "hAcc", 0) or 0) * 1e-3,
            "v_acc_m": float(getattr(msg, "vAcc", 0) or 0) * 1e-3,
            "pdop": float(getattr(msg, "pDOP", 0.0) or 0.0),
            "spoof_det_state": 0,  # updated by NAV-STATUS parse below
        }

    def _parse_sat(self, msg) -> list[dict]:
        ts = datetime.now(tz=timezone.utc).isoformat()
        num_svs = int(getattr(msg, "numSvs", 0) or 0)
        satellites = []
        for i in range(1, num_svs + 1):
            # pyubx2 uses zero-padded 2-digit suffix for repeated groups
            sfx = f"_{i:02d}"
            cn0 = getattr(msg, f"cno{sfx}", None)
            if cn0 is None:
                continue
            satellites.append({
                "timestamp": ts,
                "gnss_id": int(getattr(msg, f"gnssId{sfx}", 0) or 0),
                "sv_id": int(getattr(msg, f"svId{sfx}", 0) or 0),
                "cn0_dbhz": float(cn0),
                "elev_deg": float(getattr(msg, f"elev{sfx}", 0) or 0),
                "azim_deg": float(getattr(msg, f"azim{sfx}", 0) or 0),
                "quality_ind": int(getattr(msg, f"qualityInd{sfx}", 0) or 0),
            })
        return satellites

    def _parse_rf(self, msg) -> list[dict]:
        # Confirmed field names from pyubx2 1.3.0 on ZED-X20P:
        # jammingState_01, agcCnt_01, noisePerMS_01, jamInd_01, blockId_01
        ts = datetime.now(tz=timezone.utc).isoformat()
        n = int(getattr(msg, "nBlocks", 0) or 0)
        blocks = []
        for i in range(1, n + 1):
            sfx = f"_{i:02d}"
            blocks.append({
                "timestamp": ts,
                "block_id": int(getattr(msg, f"blockId{sfx}", i - 1) or 0),
                "jamming_state": int(getattr(msg, f"jammingState{sfx}", 0) or 0),
                "agc_cnt": int(getattr(msg, f"agcCnt{sfx}", 0) or 0),
                "noise_per_ms": int(getattr(msg, f"noisePerMS{sfx}", 0) or 0),
                "jamming_indicator": int(getattr(msg, f"jamInd{sfx}", 0) or 0),
                "ant_status": int(getattr(msg, f"antStatus{sfx}", 0) or 0),
                "ant_power": int(getattr(msg, f"antPower{sfx}", 0) or 0),
            })
        return blocks

    def _emit(self) -> None:
        if self._current_pvt is None:
            return
        sample = {
            "pvt": self._current_pvt,
            "satellites": list(self._current_sat),
            "rf": list(self._current_rf),
        }
        try:
            self.on_sample(sample)
        except Exception:
            logger.exception("on_sample error")

    def _poll_and_parse(self, ser: serial.Serial) -> None:
        """Poll all required messages and update buffers."""
        from io import BytesIO

        # Do NOT reset input buffer — device auto-outputs NAV-SAT/NAV-STATUS and
        # resetting would discard them. Explicit polls ensure we get all messages
        # even when auto-output timing doesn't align with our window.
        for cls, mid in _POLL_MSGS:
            ser.write(_ubx_frame(cls, mid))
            time.sleep(0.02)

        # Collect for 1.1 s — covers up to one full 1 Hz nav epoch wait for NAV-PVT
        deadline = time.monotonic() + 1.1
        raw = b""
        while time.monotonic() < deadline:
            avail = ser.in_waiting
            if avail:
                raw += ser.read(avail)
            else:
                time.sleep(0.02)

        if not raw:
            return

        # Parse UBX messages from the collected bytes
        ubr = UBXReader(BytesIO(raw), protfilter=2, errorhandler=lambda *_: None)
        for _, parsed in ubr:
            if parsed is None:
                continue
            identity = parsed.identity
            if identity == "NAV-PVT":
                self._current_pvt = self._parse_pvt(parsed)
            elif identity == "NAV-SAT":
                self._current_sat = self._parse_sat(parsed)
            elif identity == "MON-RF":
                self._current_rf = self._parse_rf(parsed)
            elif identity == "NAV-STATUS":
                spoof = getattr(parsed, "spoofDetState", None)
                if spoof is None:
                    flags = int(getattr(parsed, "flags", 0) or 0)
                    spoof = (flags >> 3) & 0x03
                if self._current_pvt is not None:
                    self._current_pvt["spoof_det_state"] = int(spoof)

    def _run(self) -> None:
        while self._running:
            try:
                with serial.Serial(self.port, self.baud_rate, timeout=1) as ser:
                    logger.info("Serial port opened: %s", self.port)
                    self._configure(ser)

                    while self._running:
                        t0 = time.monotonic()
                        self._poll_and_parse(ser)
                        if self._current_pvt is not None:
                            self._emit()
                        elapsed = time.monotonic() - t0
                        time.sleep(max(0.0, 1.0 - elapsed))

            except serial.SerialException as exc:
                logger.error("Serial error: %s — retry in 5 s", exc)
                if self.on_error:
                    self.on_error(str(exc))
                time.sleep(5)
            except Exception:
                logger.exception("Collector error — retry in 5 s")
                time.sleep(5)
