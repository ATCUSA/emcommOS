"""Inputs shared by every config renderer."""

from __future__ import annotations

from dataclasses import dataclass

from ..models import Operator, RadioDef, Station

RIGCTLD_ADDR = "127.0.0.1:4532"


@dataclass(frozen=True)
class RenderContext:
    operator: Operator
    station: Station
    radio: RadioDef

    @property
    def ptt(self) -> str:
        return self.station.ptt_method(self.radio)

    @property
    def alsa_device(self) -> str | None:
        return f"sysdefault:CARD={self.station.alsa_id}" if self.station.audio else None
