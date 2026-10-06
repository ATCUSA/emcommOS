"""Line-level editing of Qt/INI files that leaves unmanaged bytes untouched."""

from __future__ import annotations

from collections.abc import Mapping


def set_ini_keys(text: str, section: str, values: Mapping[str, str]) -> str:
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    header = f"[{section}]"
    start = next((i for i, line in enumerate(lines) if line.strip() == header), None)
    if start is None:
        if lines and lines[-1].strip():
            lines.append("\n")
        return "".join([*lines, header + "\n", *(f"{k}={v}\n" for k, v in values.items())])

    end = next((i for i in range(start + 1, len(lines)) if lines[i].lstrip().startswith("[")),
               len(lines))
    remaining = dict(values)
    for i in range(start + 1, end):
        if "=" in lines[i]:
            key = lines[i].split("=", 1)[0].strip()
            if key in remaining:
                lines[i] = f"{key}={remaining.pop(key)}\n"
    insert_at = end
    while insert_at > start + 1 and not lines[insert_at - 1].strip():
        insert_at -= 1
    lines[insert_at:insert_at] = [f"{k}={v}\n" for k, v in remaining.items()]
    return "".join(lines)
