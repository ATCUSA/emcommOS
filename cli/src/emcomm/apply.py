"""Plan, diff, back up and write rendered app configs for the active selection."""

from __future__ import annotations

import difflib
import os
import shutil
import subprocess
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import tomli_w

from .paths import Paths
from .render.context import RenderContext
from .render.direwolf import render_direwolf
from .render.fldigi import render_fldigi
from .render.pat import render_pat
from .render.qtini import render_wsjtx
from .render.rigctld import render_rigctld

Renderer = Callable[[str | None, RenderContext], str | None]


@dataclass(frozen=True)
class AppConfig:
    app: str
    relpath: str
    render: Renderer


APP_CONFIGS = (
    AppConfig("rigctld", ".config/emcomm/rigctld.env", render_rigctld),
    AppConfig("wsjtx", ".config/WSJT-X.ini", render_wsjtx),
    AppConfig("js8call", ".config/JS8Call.ini", render_wsjtx),
    AppConfig("fldigi", ".fldigi/fldigi_def.xml", render_fldigi),
    AppConfig("pat", ".config/pat/config.json", render_pat),
    AppConfig("direwolf", ".config/emcomm/direwolf.conf", render_direwolf),
)
SERVICES = ("emcomm-rigctld.service", "emcomm-direwolf.service", "emcomm-pat.service")

# Files fully owned by emcomm are created private; app configs use the default umask.
_PRIVATE_NEW = frozenset({".config/emcomm/rigctld.env", ".config/emcomm/direwolf.conf"})


@dataclass(frozen=True)
class FileChange:
    app: str
    path: Path
    old: str | None
    new: str


def _read(path: Path) -> str:
    # newline="" disables translation so CRLF files round-trip unchanged.
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def plan_changes(paths: Paths, ctx: RenderContext) -> list[FileChange]:
    changes = []
    for cfg in APP_CONFIGS:
        path = paths.home / cfg.relpath
        old = _read(path) if path.exists() else None
        new = cfg.render(old, ctx)
        if new is not None and new != old:
            changes.append(FileChange(cfg.app, path, old, new))
    return changes


def render_diff(changes: list[FileChange], home: Path) -> str:
    out: list[str] = []
    for c in changes:
        rel = c.path.relative_to(home).as_posix()
        out.extend(difflib.unified_diff(
            (c.old or "").splitlines(keepends=True), c.new.splitlines(keepends=True),
            fromfile=f"a/{rel}", tofile=f"b/{rel}"))
    return "".join(out)


def apply_changes(paths: Paths, changes: list[FileChange], now: datetime) -> Path | None:
    backup = paths.state / "backups" / now.strftime("%Y%m%dT%H%M%S")
    for c in changes:
        rel = c.path.relative_to(paths.home)
        if c.old is not None:
            dest = backup / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(c.path, dest)  # preserves mode
            mode = c.path.stat().st_mode & 0o7777
        else:
            mode = 0o600 if rel.as_posix() in _PRIVATE_NEW else None
        c.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = c.path.with_name(c.path.name + ".emcomm-tmp")
        # Create private, then widen to the original/default mode: never more open than before.
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(c.new)
        if mode is not None:
            os.chmod(tmp, mode)
        else:
            umask = os.umask(0)
            os.umask(umask)
            os.chmod(tmp, 0o666 & ~umask)
        os.replace(tmp, c.path)
    return backup if backup.exists() else None


def save_active(paths: Paths, callsign: str, station: str) -> None:
    paths.active_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    paths.active_file.write_text(tomli_w.dumps({"operator": callsign, "station": station}))


def load_active(paths: Paths) -> dict | None:
    if not paths.active_file.is_file():
        return None
    return tomllib.loads(paths.active_file.read_text())


def restart_services(run: Callable = subprocess.run) -> bool:
    """Restart emcomm user services that are already running; never starts stopped ones."""
    try:
        result = run(["systemctl", "--user", "try-restart", *SERVICES],
                     capture_output=True, text=True)
    except FileNotFoundError:
        return False
    return result.returncode == 0
