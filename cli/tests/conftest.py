from pathlib import Path

import pytest

from emcomm.paths import Paths

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def paths(tmp_path) -> Paths:
    return Paths(etc=tmp_path / "etc/emcomm", share=REPO_ROOT, home=tmp_path / "home",
                 udev_rules=tmp_path / "udev", sysfs=tmp_path / "sys")
