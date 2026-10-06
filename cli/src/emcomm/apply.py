"""Plan, diff, back up and write rendered app configs for the active selection."""

from __future__ import annotations

import difflib
import fnmatch
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
from .render.pipewire import render_pipewire
from .render.qtini import render_wsjtx
from .render.rigctld import render_rigctld
from .render.wfview import render_wfview
from .validation import ProfileError

Renderer = Callable[[str | None, RenderContext], str | None]


@dataclass(frozen=True)
class AppConfig:
    app: str
    relpath: str
    render: Renderer


APP_CONFIGS = (
    AppConfig("rigctld", ".config/emcomm/rigctld.env", render_rigctld),
    AppConfig("wfview", ".config/wfview/wfview.conf", render_wfview),
    AppConfig("pipewire", ".config/pipewire/pipewire.conf.d/60-emcomm-{station}.conf",
              render_pipewire),
    AppConfig("wsjtx", ".config/WSJT-X.ini", render_wsjtx),
    AppConfig("js8call", ".config/JS8Call.ini", render_wsjtx),
    AppConfig("fldigi", ".fldigi/fldigi_def.xml", render_fldigi),
    AppConfig("pat", ".config/pat/config.json", render_pat),
    AppConfig("direwolf", ".config/emcomm/direwolf.conf", render_direwolf),
)
SERVICES = ("emcomm-rigctld.service", "emcomm-direwolf.service", "emcomm-pat.service")

# Files fully owned by emcomm are created private; app configs use the default umask.
_PRIVATE_NEW = frozenset({".config/emcomm/rigctld.env", ".config/emcomm/direwolf.conf"})
_PRIVATE_NEW_PATTERNS = (".config/pipewire/pipewire.conf.d/60-emcomm-*.conf",)


def _is_private_new(rel: str) -> bool:
    return rel in _PRIVATE_NEW or any(fnmatch.fnmatchcase(rel, p) for p in _PRIVATE_NEW_PATTERNS)


@dataclass(frozen=True)
class FileChange:
    app: str
    path: Path
    old: str | None
    new: str
    delete: bool = False


def _read(path: Path) -> str:
    # newline="" disables translation so CRLF files round-trip unchanged.
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def plan_changes(paths: Paths, ctx: RenderContext) -> list[FileChange]:
    changes = []
    for cfg in APP_CONFIGS:
        path = paths.home / cfg.relpath.format(station=ctx.station.name)
        real = _real(path)
        old = _read(real) if real.exists() else None
        new = cfg.render(old, ctx)
        if new is not None and new != old:
            changes.append(FileChange(cfg.app, path, old, new))
    changes.extend(_stale_dropins(paths, ctx, {c.path for c in changes}))
    return changes


_DROPIN_GLOB = ".config/pipewire/pipewire.conf.d/60-emcomm-*.conf"


def _stale_dropins(paths: Paths, ctx: RenderContext, skip: set[Path]) -> list[FileChange]:
    """Drop-ins of other kits are emcomm-owned and stale once another station is active."""
    keep = paths.home / ".config/pipewire/pipewire.conf.d" / f"60-emcomm-{ctx.station.name}.conf"
    out = []
    for path in sorted(paths.home.glob(_DROPIN_GLOB)):
        if path == keep or path in skip:
            continue
        out.append(FileChange("pipewire", path, _read(_real(path)), "", delete=True))
    return out


def render_diff(changes: list[FileChange], home: Path) -> str:
    out: list[str] = []
    for c in changes:
        rel = c.path.relative_to(home).as_posix()
        out.extend(difflib.unified_diff(
            (c.old or "").splitlines(keepends=True), c.new.splitlines(keepends=True),
            fromfile=f"a/{rel}", tofile="/dev/null" if c.delete else f"b/{rel}"))
    return "".join(out)


def _real(path: Path) -> Path:
    """Resolve a symlinked target to the file that really holds the content."""
    if path.is_symlink():
        if not path.exists():
            raise ProfileError(f"{path} is a broken symlink; fix or remove it")
        return path.resolve()
    return path


def _new_backup_dir(root: Path, now: datetime) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    base = now.strftime("%Y%m%dT%H%M%S.%f")
    n = 0
    while True:
        candidate = root / (base if n == 0 else f"{base}-{n}")
        try:
            candidate.mkdir(exist_ok=False)
        except FileExistsError:
            n += 1
            continue
        return candidate


def _write(real: Path, new: str, mode: int | None) -> None:
    real.parent.mkdir(parents=True, exist_ok=True)
    tmp = real.with_name(real.name + ".emcomm-tmp")
    try:
        # Create private, then widen to the original/default mode: never more open than before.
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(new)
        if mode is not None:
            os.chmod(tmp, mode)
        else:
            umask = os.umask(0)
            os.umask(umask)
            os.chmod(tmp, 0o666 & ~umask)
        os.replace(tmp, real)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


def apply_changes(paths: Paths, changes: list[FileChange], now: datetime) -> Path | None:
    targets = [(c, _real(c.path)) for c in changes]  # validates symlinks before any write
    backup = _new_backup_dir(paths.state / "backups", now)
    # Phase 1: back up everything first.
    for c, real in targets:
        if c.old is not None:
            dest = backup / c.path.relative_to(paths.home)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(real, dest)  # preserves mode
    # Phase 2: write.
    written: list[Path] = []
    for c, real in targets:
        rel = c.path.relative_to(paths.home)
        try:
            if c.delete:
                c.path.unlink(missing_ok=True)  # removes a symlink itself, not its target
            else:
                if c.old is not None:
                    mode = real.stat().st_mode & 0o7777
                else:
                    mode = 0o600 if _is_private_new(rel.as_posix()) else None
                _write(real, c.new, mode)
        except OSError as exc:
            pending = [str(x.path) for x, _ in targets if x.path not in written
                       and x.path != c.path]
            raise ProfileError(
                f"failed {'removing' if c.delete else 'writing'} {c.path}: {exc}. "
                f"already written: {', '.join(map(str, written)) or 'none'}; "
                f"not written: {', '.join([str(c.path), *pending])}. "
                f"Originals are in {backup}; restore by copying them back under {paths.home}."
            ) from exc
        written.append(c.path)
    if any(backup.iterdir()):
        return backup
    backup.rmdir()
    return None


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
