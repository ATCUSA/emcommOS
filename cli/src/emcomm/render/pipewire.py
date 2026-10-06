"""Per-kit PipeWire virtual devices for LAN stations (wfview has no Linux audio devices)."""

from __future__ import annotations

from .context import RenderContext

NODE = """    {{ factory = adapter
         args = {{
           factory.name     = support.null-audio-sink
           node.name        = "{name}"
           node.description = "{description}"
           media.class      = Audio/Sink
           audio.position   = [ MONO ]
           object.linger    = true
           monitor.channel-volumes = true
         }}
       }}"""


def render_pipewire(existing: str | None, ctx: RenderContext) -> str | None:
    st = ctx.station
    if not st.virtual_audio:
        return None
    rx = NODE.format(name=st.rx_sink, description=f"emcomm {st.name} RX (radio audio from wfview)")
    tx = NODE.format(name=st.tx_sink, description=f"emcomm {st.name} TX (app audio to wfview)")
    return (f"# Managed by emcomm: virtual audio for LAN station {st.name}.\n"
            f"context.objects = [\n{rx}\n{tx}\n]\n")
