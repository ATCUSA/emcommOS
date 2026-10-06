"""Filesystem locations used by emcomm, relocatable for tests."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Paths:
    etc: Path
    share: Path
    home: Path
    udev_rules: Path
    sysfs: Path

    @property
    def xdg_config(self) -> Path:
        return self.home / ".config"

    @property
    def user_config(self) -> Path:
        return self.xdg_config / "emcomm"

    @property
    def state(self) -> Path:
        return self.home / ".local/state/emcomm"

    @property
    def operators_dir(self) -> Path:
        return self.user_config / "operators"

    @property
    def active_file(self) -> Path:
        return self.user_config / "active.toml"

    @property
    def stations_dir(self) -> Path:
        return self.etc / "stations"

    @property
    def radios_dir(self) -> Path:
        return self.share / "radios"

    @property
    def ansible_dir(self) -> Path:
        return self.share / "ansible"

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> Paths:
        root = env.get("EMCOMM_ROOT")
        if root:
            r = Path(root)
            return cls(
                etc=r / "etc/emcomm",
                share=Path(env.get("EMCOMM_SHARE", r / "opt/emcomm/share/emcomm")),
                home=r / "home",
                udev_rules=r / "etc/udev/rules.d",
                sysfs=Path(env.get("EMCOMM_SYSFS", r / "sys")),
            )
        return cls(
            etc=Path("/etc/emcomm"),
            share=Path(env.get("EMCOMM_SHARE", "/opt/emcomm/share/emcomm")),
            home=Path.home(),
            udev_rules=Path("/etc/udev/rules.d"),
            sysfs=Path(env.get("EMCOMM_SYSFS", "/sys")),
        )
