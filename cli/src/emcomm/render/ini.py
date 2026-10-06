"""Line-level editing of Qt/INI files that leaves unmanaged bytes untouched.

Preserves the file's exact line endings (CRLF or LF) and BOM if present. Appends a final
newline if the file lacks one. Manages only named keys within the specified section; all
other content (including unmanaged keys and different sections) is byte-for-byte preserved.
"""

from __future__ import annotations

from collections.abc import Mapping


def set_ini_keys(text: str, section: str, values: Mapping[str, str]) -> str:
    # Validate values don't contain newlines
    for k, v in values.items():
        if "\r" in v or "\n" in v:
            raise ValueError(f"value for {k!r} must not contain newlines")

    # Detect BOM
    has_bom = text.startswith("﻿")
    bom = "﻿" if has_bom else ""
    working = text[len(bom):] if has_bom else text

    # Detect line ending: CRLF if present, else LF
    eol = "\r\n" if "\r\n" in working else "\n"

    # Split only on \n (not str.splitlines which splits on many Unicode separators)
    # but keep the original line terminators
    if not working:
        lines = []
    else:
        parts = working.split("\n")
        lines = []
        for part in parts[:-1]:
            # Restore the \n we split on, keeping any \r that precedes it
            lines.append(part + "\n")
        # Last part: add if non-empty or if original ended with \n
        if parts[-1]:
            lines.append(parts[-1])

    header = f"[{section}]"
    # Find the header, accounting for potential BOM and strip whitespace
    start = None
    for i, line in enumerate(lines):
        # Strip line ending to get clean content
        clean_line = line.rstrip("\r\n")
        if clean_line.strip() == header:
            start = i
            break

    if start is None:
        # Section doesn't exist; create and append it
        result = bom + "".join(lines)
        if result and not result.endswith(("\n", "\r\n")):
            result += eol
        if result:
            # Add blank line before new section if there's existing content
            result += eol
        result += header + eol
        for k, v in values.items():
            result += f"{k}={v}{eol}"
        return result

    # Find end of section (next line starting with '[')
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].lstrip().startswith("["):
            end = i
            break

    # Update all occurrences of managed keys in the section
    for i in range(start + 1, end):
        if "=" in lines[i]:
            key_part = lines[i].split("=", 1)[0].strip()
            if key_part in values:
                # Preserve the line terminator
                terminator = "\r\n" if lines[i].endswith("\r\n") else "\n" if lines[i].endswith("\n") else ""
                lines[i] = f"{key_part}={values[key_part]}{terminator}"

    # Determine which keys were already in the section (updated)
    updated_keys = set()
    for i in range(start + 1, end):
        if "=" in lines[i]:
            key_part = lines[i].split("=", 1)[0].strip()
            if key_part in values:
                updated_keys.add(key_part)

    remaining = {k: v for k, v in values.items() if k not in updated_keys}

    if remaining:
        # Find where to insert: before the next section or at end, skipping blank lines
        insert_at = end
        while insert_at > start + 1 and not lines[insert_at - 1].strip():
            insert_at -= 1

        new_lines = [f"{k}={v}{eol}" for k, v in remaining.items()]
        lines[insert_at:insert_at] = new_lines

    result = bom + "".join(lines)
    # Add final newline if missing
    if result and not result.endswith(("\n", "\r\n")):
        result += eol
    return result
