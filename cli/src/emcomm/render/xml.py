"""Element-level editing of flat XML settings files (fldigi_def.xml style).

Preserves the file's exact line endings (CRLF or LF) and XML attributes. Elements with
attributes are matched and updated with attributes preserved. Appends a final newline if
the file lacks one. Tags inside comments are not modified (fldigi doesn't write comments).
"""

from __future__ import annotations

import html
import re
from collections.abc import Mapping


def set_xml_elements(text: str, root: str, values: Mapping[str, str]) -> str:
    # Validate values don't contain newlines
    for k, v in values.items():
        if "\r" in v or "\n" in v:
            raise ValueError(f"value for {k!r} must not contain newlines")

    if not text.strip():
        text = f"<{root}>\n</{root}>\n"

    # Detect line ending: CRLF if present, else LF
    eol = "\r\n" if "\r\n" in text else "\n"

    for tag, value in values.items():
        escaped_value = html.escape(value, quote=False)
        # Match elements with optional attributes: <TAG...>content</TAG> or <TAG.../>
        # Use re.escape to handle special regex characters in tag names
        escaped_tag = re.escape(tag)
        # Try self-closing first (higher priority) to avoid incorrect span to later </TAG>
        # Self-closing: <TAG(\s[^>]*?)?\s*/> (non-greedy attrs, optional whitespace before />)
        # Regular: <TAG(\s[^>]*?)?>.*?</TAG> (non-greedy attrs and content)
        pattern = re.compile(
            rf"<{escaped_tag}(\s[^>]*?)?\s*/>|<{escaped_tag}(\s[^>]*?)?>.*?</{escaped_tag}>",
            re.DOTALL
        )

        def replacer(match: re.Match, tag=tag, escaped_value=escaped_value) -> str:
            # Extract attributes (group 1 for self-closing, group 2 for regular)
            attrs = match.group(1) or match.group(2) or ""
            # Convert all matches (self-closing or regular) to regular elements with content
            return f"<{tag}{attrs}>{escaped_value}</{tag}>"

        text, n = pattern.subn(replacer, text, count=1)
        if n == 0:
            close = text.rfind(f"</{root}>")
            if close < 0:
                raise ValueError(f"settings file has no </{root}> element")
            element = f"<{tag}>{escaped_value}</{tag}>"
            text = text[:close] + element + eol + text[close:]

    # Add final newline if missing
    if text and not text.endswith(("\n", "\r\n")):
        text += eol
    return text
