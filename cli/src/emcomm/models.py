"""Operator, radio and station data types plus input normalization."""

from __future__ import annotations

import re
from dataclasses import dataclass

CALLSIGN_RE = re.compile(
    r"^(?=[A-Z0-9/]{3,15}$)(?:[A-Z0-9]{1,4}/)?[A-Z0-9]*\d[A-Z0-9]*[A-Z](?:/[A-Z0-9]{1,4})?$"
)
GRID_RE = re.compile(r"^[A-R]{2}\d{2}(?:[A-X]{2})?$", re.IGNORECASE)
PTT_METHODS = ("cat", "rts", "dtr", "vox")
CONTROL_MODES = ("direct", "wfview")


def normalize_callsign(raw: str) -> str:
    value = raw.strip().upper()
    if not CALLSIGN_RE.match(value):
        raise ValueError(f"invalid callsign {raw!r}")
    return value


def normalize_grid(raw: str) -> str:
    value = raw.strip()
    if not value:
        return ""
    if not GRID_RE.match(value):
        raise ValueError(f"invalid Maidenhead grid {raw!r}")
    return value[:2].upper() + value[2:4] + value[4:].lower()


def ax25_callsign(callsign: str) -> str:
    """Base call without portable prefixes/suffixes (AX.25 allows at most 6 chars + SSID)."""
    parts = [p for p in callsign.split("/") if any(c.isdigit() for c in p)]
    if not parts:
        return callsign

    def has_digit_then_letter(s: str) -> bool:
        """Check if string has a digit followed (later) by a letter."""
        for i, c in enumerate(s):
            if c.isdigit() and any(ch.isalpha() for ch in s[i + 1 :]):
                return True
        return False

    # Prefer parts matching base-callsign shape (digit followed by letter);
    # on ties prefer later part
    return max(parts, key=lambda p: (has_digit_then_letter(p), parts.index(p)))


@dataclass(frozen=True)
class Operator:
    callsign: str
    name: str = ""
    grid: str = ""


@dataclass(frozen=True)
class UsbHint:
    vendor_id: str = ""
    product_id: str = ""
    serial_prefix: str = ""
    product_contains: str = ""
    interface: str = ""


@dataclass(frozen=True)
class RadioDef:
    id: str
    vendor: str
    model: str
    hamlib_model: int
    baud: int
    ptt: str
    set_conf: tuple[tuple[str, str], ...] = ()
    cat_hints: tuple[UsbHint, ...] = ()
    audio_hints: tuple[UsbHint, ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        return f"{self.vendor} {self.model}"


@dataclass(frozen=True)
class UsbMatch:
    vendor_id: str
    product_id: str
    serial: str = ""
    interface: str = ""


@dataclass(frozen=True)
class Station:
    name: str
    radio: str
    cat: UsbMatch | None = None
    audio: UsbMatch | None = None
    ptt: str | None = None
    control: str = "direct"
    virtual_audio: bool = False

    @property
    def rx_sink(self) -> str:
        return f"emcomm-{self.name}-rx"

    @property
    def tx_sink(self) -> str:
        return f"emcomm-{self.name}-tx"

    @property
    def cat_link(self) -> str:
        return f"/dev/emcomm/cat-{self.name}"

    @property
    def alsa_id(self) -> str:
        return "EMCOMM_" + self.name.upper().replace("-", "_")

    def ptt_method(self, radio: RadioDef) -> str:
        return self.ptt or radio.ptt
