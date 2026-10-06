"""WSJT-X / JS8Call [Configuration] keys pointing at the rigctld hub."""

from __future__ import annotations

from .context import RIGCTLD_ADDR, RenderContext
from .ini import set_ini_keys

# QSettings serialization of TransceiverFactory::PTTMethod; both enum names are 14 chars.
PTT_VARIANT = (
    r"@Variant(\0\0\0\x7f\0\0\0\x1eTransceiverFactory::PTTMethod\0\0\0\0\xfPTT_method_{}\0)"
)


def wsjtx_values(ctx: RenderContext) -> dict[str, str]:
    values = {
        "MyCall": ctx.operator.callsign,
        "Rig": "Hamlib NET rigctl",
        "CATNetworkPort": RIGCTLD_ADDR,
        "PTTMethod": PTT_VARIANT.format("VOX" if ctx.ptt == "vox" else "CAT"),
    }
    if ctx.operator.grid:
        values["MyGrid"] = ctx.operator.grid
    if ctx.sound_in:
        values["SoundInName"] = f'"{ctx.sound_in}"'
    if ctx.sound_out:
        values["SoundOutName"] = f'"{ctx.sound_out}"'
    return values


def render_wsjtx(existing: str | None, ctx: RenderContext) -> str:
    return set_ini_keys(existing or "", "Configuration", wsjtx_values(ctx))
