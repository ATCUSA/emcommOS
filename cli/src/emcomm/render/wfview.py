"""wfview.conf: enable wfview's rigctld-compatible server for the emcomm hub proxy."""

from __future__ import annotations

from .context import RenderContext
from .ini import set_ini_keys
from .rigctld import WFVIEW_RIGCTL_ADDR


def render_wfview(existing: str | None, ctx: RenderContext) -> str | None:
    if ctx.station.control != "wfview":
        return None
    port = WFVIEW_RIGCTL_ADDR.rsplit(":", 1)[1]
    return set_ini_keys(existing or "", "LAN", {"EnableRigCtlD": "true", "RigCtlPort": port})
