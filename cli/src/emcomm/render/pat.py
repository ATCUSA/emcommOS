"""Pat config.json: identity plus an "emcomm" hamlib rig on the rigctld hub.

Secrets (secure_login_password) are never written; Pat prompts for them.
"""

from __future__ import annotations

import copy
import json

from .context import RIGCTLD_ADDR, RenderContext

# Mirrors Pat v1.0.0 cfg.DefaultConfig for a fresh file.
PAT_DEFAULTS: dict = {
    "mycall": "",
    "secure_login_password": "",
    "auxiliary_addresses": [],
    "locator": "",
    "service_codes": ["PUBLIC"],
    "http_addr": "localhost:8080",
    "motd": ["Open source Winlink client - getpat.io"],
    "connect_aliases": {"telnet": "telnet://{mycall}:CMSTelnet@cms.winlink.org:8772/wl2k"},
    "listen": [],
    "hamlib_rigs": {},
    "auto_download_size_limit": -1,
    "ax25": {"engine": "agwpe", "rig": "",
             "beacon": {"every": 3600, "message": "Winlink P2P", "destination": "IDENT"}},
    "agwpe": {"addr": "localhost:8000", "radio_port": 0},
    "ardop": {"addr": "localhost:8515", "rig": "", "ptt_ctrl": False, "beacon_interval": 0,
              "cwid_enabled": True},
    "telnet": {"listen_addr": ":8774", "password": ""},
    "varahf": {"addr": "localhost:8300", "bandwidth": 2300, "rig": "", "ptt_ctrl": False},
    "varafm": {"addr": "localhost:8300", "rig": "", "ptt_ctrl": False},
    "gpsd": {"addr": "localhost:2947", "enable_http": False, "allow_forms": False,
             "use_server_time": False},
}


def render_pat(existing: str | None, ctx: RenderContext) -> str:
    if existing and existing.strip():
        try:
            data = json.loads(existing)
        except json.JSONDecodeError as exc:
            raise ValueError(f"pat config.json is not valid JSON: {exc}") from None
    else:
        data = copy.deepcopy(PAT_DEFAULTS)
    data["mycall"] = ctx.operator.callsign
    if ctx.operator.grid:
        data["locator"] = ctx.operator.grid
    data.setdefault("hamlib_rigs", {})["emcomm"] = {
        "network": "tcp", "address": RIGCTLD_ADDR, "VFO": ""}
    ptt_ctrl = ctx.ptt != "vox"
    for transport in ("ardop", "varahf"):
        section = data.setdefault(transport, {})
        section["rig"] = "emcomm"
        section["ptt_ctrl"] = ptt_ctrl
    data.setdefault("ax25", {})["rig"] = "emcomm"
    return json.dumps(data, indent=2) + "\n"
