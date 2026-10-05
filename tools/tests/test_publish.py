import json
from pathlib import Path

from emcomm_build.container import Engine
from emcomm_build.model import load_targets
from emcomm_build.publish import place_packages, publish_command, write_manifests


def make_dist(root: Path) -> Path:
    dist = root / "dist"
    (dist / "debian-13/amd64").mkdir(parents=True)
    (dist / "debian-13/amd64/emcomm-a_1.0-1+deb13_amd64.deb").write_text("d")
    (dist / "fedora-44/arm64").mkdir(parents=True)
    (dist / "fedora-44/arm64/emcomm-a-1.0-1.fc44.aarch64.rpm").write_text("r")
    return dist


def test_place_and_manifest(fake_repo, tmp_path):
    targets = load_targets(fake_repo)
    repo = tmp_path / "public/testing"
    placed = place_packages(make_dist(tmp_path), repo, targets)
    assert (repo / "deb/pool/debian-13/emcomm-a_1.0-1+deb13_amd64.deb").is_file()
    assert (repo / "rpm/fedora-44/aarch64/emcomm-a-1.0-1.fc44.aarch64.rpm").is_file()
    assert set(placed) == {("debian-13", "amd64"), ("fedora-44", "arm64")}
    write_manifests(repo, targets)
    m = json.loads((repo / "manifest/debian-13-amd64.json").read_text())
    assert m == {"target": "debian-13", "arch": "amd64",
                 "files": ["deb/pool/debian-13/emcomm-a_1.0-1+deb13_amd64.deb"]}
    assert not (repo / "manifest/debian-13-arm64.json").exists()
    assert json.loads((repo / "manifest/fedora-44-arm64.json").read_text())["files"] == [
        "rpm/fedora-44/aarch64/emcomm-a-1.0-1.fc44.aarch64.rpm"]


def test_publish_command(fake_repo, tmp_path):
    targets = load_targets(fake_repo)
    repo = tmp_path / "repo"
    place_packages(make_dist(tmp_path), repo, targets)
    cmd = publish_command(Engine(), Path("/src"), repo, targets,
                          ["rpm/fedora-44/aarch64/x.rpm"], tmp_path / "k.asc", tmp_path / "pp")
    assert "DEB_SUITES=debian-13" in cmd
    assert "RPM_DIRS=rpm/fedora-44/aarch64" in cmd
    assert "NEW_RPMS=rpm/fedora-44/aarch64/x.rpm" in cmd
    assert f"{tmp_path / 'k.asc'}:/keys/signing.asc:ro,z" in cmd
    assert cmd[-3:] == ["docker.io/library/debian:13", "bash", "/emcomm/tools/container/publish.sh"]
