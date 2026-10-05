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
                          tmp_path / "k.asc", tmp_path / "pp")
    assert "DEB_SUITES=debian-13" in cmd
    assert "RPM_DIRS=rpm/fedora-44/aarch64" in cmd
    assert not any(c.startswith("NEW_RPMS") for c in cmd)
    assert f"{tmp_path / 'k.asc'}:/keys/signing.asc:ro,z" in cmd
    assert cmd[-3:] == ["docker.io/library/debian:13", "bash", "/emcomm/tools/container/publish.sh"]


def test_publish_command_absolute_mounts(fake_repo, tmp_path, monkeypatch):
    targets = load_targets(fake_repo)
    monkeypatch.chdir(tmp_path)
    repo = Path("rel-repo")
    place_packages(make_dist(tmp_path), repo, targets)
    from emcomm_build.publish import publish
    calls = []
    (tmp_path / "k.asc").write_text("")
    monkeypatch.setattr("emcomm_build.publish.primary_fingerprint", lambda p: "AA")
    publish(Path("."), Path("dist"), repo, targets, Path("k.asc"), Path("pp"),
            Path("k.asc"), run=lambda cmd, **kw: calls.append(cmd))
    cmd = calls[0]
    mounts = [cmd[i + 1].split(":")[0] for i, c in enumerate(cmd) if c == "-v"]
    assert len(mounts) == 4 and all(m.startswith("/") for m in mounts)


def test_place_skips_existing(fake_repo, tmp_path):
    targets = load_targets(fake_repo)
    repo = tmp_path / "repo"
    dist = make_dist(tmp_path)
    place_packages(dist, repo, targets)
    existing = repo / "deb/pool/debian-13/emcomm-a_1.0-1+deb13_amd64.deb"
    existing.write_text("signed-original")
    assert place_packages(dist, repo, targets) == {}
    assert existing.read_text() == "signed-original"


def test_public_key_mismatch(fake_repo, tmp_path):
    import shutil
    import subprocess

    import pytest

    from emcomm_build.model import DefinitionError
    from emcomm_build.publish import publish
    if shutil.which("gpg") is None:
        pytest.skip("gpg not installed")
    keys = []
    for n in ("one", "two"):
        home = tmp_path / f"h{n}"
        home.mkdir(mode=0o700)
        env = {"GNUPGHOME": str(home), "PATH": "/usr/bin:/bin"}
        base = ["gpg", "--batch", "--passphrase", ""]
        subprocess.run([*base, "--quick-gen-key", n, "ed25519", "sign", "never"],
                       check=True, env=env, capture_output=True)
        sec, pub = tmp_path / f"{n}.sec", tmp_path / f"{n}.pub"
        sec.write_bytes(subprocess.run([*base, "--armor", "--export-secret-keys"], env=env,
                                       check=True, capture_output=True).stdout)
        pub.write_bytes(subprocess.run(["gpg", "--armor", "--export"], env=env,
                                       check=True, capture_output=True).stdout)
        keys.append((sec, pub))
    targets = load_targets(fake_repo)
    with pytest.raises(DefinitionError, match="does not match"):
        publish(tmp_path, make_dist(tmp_path), tmp_path / "r", targets, keys[0][0],
                tmp_path / "pp", keys[1][1], run=lambda *a, **k: None)
