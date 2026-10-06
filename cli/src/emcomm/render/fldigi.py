"""fldigi_def.xml: identity plus hamlib NET rigctl (model 2) via the hub."""

from __future__ import annotations

from .context import RIGCTLD_ADDR, RenderContext
from .xml import set_xml_elements


def fldigi_values(ctx: RenderContext) -> dict[str, str]:
    values = {
        "MYCALL": ctx.operator.callsign,
        "CHKUSEHAMLIBIS": "1",
        "HAMRIGMODEL": "2",
        "HAMRIGNAME": "",
        "HAMRIGDEVICE": RIGCTLD_ADDR,
        "HAMLIBCMDPTT": "0" if ctx.ptt == "vox" else "1",
        "CHKUSERIGCATIS": "0",
        "CHKUSEXMLRPCIS": "0",
    }
    if ctx.operator.name:
        values["MYNAME"] = ctx.operator.name
    if ctx.operator.grid:
        values["MYLOC"] = ctx.operator.grid
    return values


def render_fldigi(existing: str | None, ctx: RenderContext) -> str:
    return set_xml_elements(existing or "", "FLDIGI_DEFS", fldigi_values(ctx))
