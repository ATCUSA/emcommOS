"""Element-level editing of flat XML settings files (fldigi_def.xml style)."""

from __future__ import annotations

import html
import re
from collections.abc import Mapping


def set_xml_elements(text: str, root: str, values: Mapping[str, str]) -> str:
    if not text.strip():
        text = f"<{root}>\n</{root}>\n"
    for tag, value in values.items():
        element = f"<{tag}>{html.escape(value, quote=False)}</{tag}>"
        pattern = re.compile(rf"<{tag}>.*?</{tag}>|<{tag}\s*/>", re.DOTALL)
        text, n = pattern.subn(lambda _m, e=element: e, text, count=1)
        if n == 0:
            close = text.rfind(f"</{root}>")
            if close < 0:
                raise ValueError(f"settings file has no </{root}> element")
            text = text[:close] + element + "\n" + text[close:]
    return text
