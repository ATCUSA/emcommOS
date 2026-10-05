import subprocess

from emcomm_build.model import Upstream
from emcomm_build.upstream import is_newer, list_tags, pick_latest, version_key


def test_version_key_orders_numerically():
    assert version_key("4.10.0") > version_key("4.9.9")


def test_pick_latest_filters_by_pattern():
    tags = ["v3.0.1", "v3.0.2", "v3.2.0-rc1", "wsjtx-2.7.0"]
    assert pick_latest(tags, r"v(\d+\.\d+\.\d+)") == "3.0.2"


def test_pick_latest_bare_versions():
    assert pick_latest(["1.7", "1.8", "1.8.1", "1.8-beta1"], r"(\d+\.\d+(?:\.\d+)?)") == "1.8.1"


def test_pick_latest_none_when_nothing_matches():
    assert pick_latest(["foo"], r"v(\d+)") is None


def test_is_newer():
    assert is_newer("4.7.2", "4.7.1")
    assert not is_newer("4.7.2", "4.7.2")


def test_list_tags_github_skips_prereleases():
    releases = [
        {"tag_name": "v1.0.0", "draft": False, "prerelease": False},
        {"tag_name": "v1.1.0-rc1", "draft": False, "prerelease": True},
        {"tag_name": "v0.9.0", "draft": True, "prerelease": False},
    ]
    up = Upstream(type="github-releases", tag_pattern=r"v(.*)", repo="la5nta/pat")
    seen = []

    def fake_http(url):
        seen.append(url)
        return releases

    assert list_tags(up, http_json=fake_http) == ["v1.0.0"]
    assert seen == ["https://api.github.com/repos/la5nta/pat/releases?per_page=100"]


def test_list_tags_git():
    out = "abc\trefs/tags/v4.2.12\ndef\trefs/tags/v4.2.13\n"

    def fake_run(cmd, **kwargs):
        assert cmd[:4] == ["git", "ls-remote", "--tags", "--refs"]
        return subprocess.CompletedProcess(cmd, 0, stdout=out)

    up = Upstream(type="git-tags", tag_pattern=r"v(.*)", url="https://git.code.sf.net/p/fldigi/fldigi")
    assert list_tags(up, run=fake_run) == ["v4.2.12", "v4.2.13"]
