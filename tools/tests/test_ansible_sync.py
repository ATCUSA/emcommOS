import yaml
from conftest import REAL_ROOT

from emcomm_build.model import load_targets

VARS = REAL_ROOT / "ansible/ansible_collections/emcomm/station/roles/base/vars/Debian.yml"


def test_backports_pin_matches_targets():
    repo = load_targets(REAL_ROOT)["debian-13"].extra_repos[0]
    role = yaml.safe_load(VARS.read_text())
    assert role["emcomm_backports_packages"] == list(repo.pin_packages)
    assert role["emcomm_backports_priority"] == repo.pin_priority
    assert f"Suites: {role['emcomm_backports_suite']}" in repo.deb822
