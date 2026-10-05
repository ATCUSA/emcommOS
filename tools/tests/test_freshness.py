import urllib.error

from emcomm_build.freshness import debian_versions, fedora_version, report
from emcomm_build.model import Upstream

MADISON = """\
 wsjtx | 2.7.0+repack-1   | trixie           | source, amd64, arm64
 wsjtx | 3.0.2+repack-1~bpo13+1 | trixie-backports | source, amd64, arm64
 wsjtx | 3.0.2+repack-1   | forky            | source, amd64, arm64
"""


def test_debian_versions_strip_revision():
    v = debian_versions("wsjtx", http_text=lambda url: MADISON)
    assert v == {"trixie": "2.7.0", "trixie-backports": "3.0.2", "forky": "3.0.2"}


def test_fedora_version():
    assert fedora_version("wsjtx", 44, http_json=lambda url: {"version": "3.0.1"}) == "3.0.1"

    def missing(url):
        raise LookupError

    assert fedora_version("pat", 44, http_json=missing) is None


def test_report_marks_current():
    entries = {"wsjtx": {"upstream": Upstream("github-releases", r"v(\d+\.\d+\.\d+)", repo="x"),
                         "debian": "wsjtx", "fedora": "wsjtx"}}
    rows = report(entries, tags=lambda up: ["v3.0.2", "v3.0.1"],
                  deb=lambda pkg: {"trixie": "2.7.0", "trixie-backports": "3.0.2"},
                  fed=lambda pkg, rel: "3.0.1")
    assert rows == [{"app": "wsjtx", "upstream": "3.0.2", "trixie": "2.7.0",
                     "trixie-backports": "=3.0.2", "f43": "3.0.1", "f44": "3.0.1"}]


def test_report_upstream_error_urlerror(capsys):
    """Tags raises URLError for one app; that app's upstream is "?" but distro columns render."""
    def failing_tags(up):
        if up.repo == "fail-app":
            raise urllib.error.URLError("connection failed")
        return ["v2.0.0"]

    entries = {
        "app-a": {"upstream": Upstream("github-releases", r"v(\d+\.\d+\.\d+)", repo="fail-app"),
                  "debian": "app-a", "fedora": "app-a"},
        "app-b": {"upstream": Upstream("github-releases", r"v(\d+\.\d+\.\d+)", repo="ok-app"),
                  "debian": "app-b", "fedora": "app-b"},
    }
    rows = report(entries, tags=failing_tags,
                  deb=lambda pkg: {suite: "1.0.0" for suite in ["trixie", "trixie-backports"]},
                  fed=lambda pkg, rel: "1.0.0")

    # app-a should have "?" upstream but still render distro columns
    assert rows[0]["app"] == "app-a"
    assert rows[0]["upstream"] == "?"
    assert rows[0]["trixie"] == "1.0.0"
    assert rows[0]["trixie-backports"] == "1.0.0"

    # app-b should be unaffected
    assert rows[1]["app"] == "app-b"
    assert rows[1]["upstream"] == "2.0.0"

    # Check stderr warning
    captured = capsys.readouterr()
    assert "app-a upstream" in captured.err


def test_report_debian_error(capsys):
    """Debian lookup failure shows "?" in trixie/trixie-backports."""
    def failing_deb(pkg):
        raise OSError("network error")

    entries = {"pkg-a": {"upstream": Upstream("github-releases", r"v(\d+\.\d+\.\d+)", repo="x"),
                         "debian": "pkg-a", "fedora": "pkg-a"}}
    rows = report(entries, tags=lambda up: ["v2.0.0"],
                  deb=failing_deb,
                  fed=lambda pkg, rel: "1.0.0")

    assert rows[0]["trixie"] == "?"
    assert rows[0]["trixie-backports"] == "?"
    assert rows[0]["f43"] == "1.0.0"  # fedora still works

    captured = capsys.readouterr()
    assert "pkg-a debian" in captured.err


def test_report_fedora_error(capsys):
    """Fedora lookup failure shows "?" in f43/f44."""
    def failing_fed(pkg, rel):
        raise OSError("network error")

    entries = {"pkg-a": {"upstream": Upstream("github-releases", r"v(\d+\.\d+\.\d+)", repo="x"),
                         "debian": "pkg-a", "fedora": "pkg-a"}}
    rows = report(entries, tags=lambda up: ["v1.0.0"],
                  deb=lambda pkg: {"trixie": "1.0.0", "trixie-backports": "1.0.0"},
                  fed=failing_fed)

    assert rows[0]["trixie"] == "=1.0.0"  # debian still works (matches upstream)
    assert rows[0]["f43"] == "?"
    assert rows[0]["f44"] == "?"

    captured = capsys.readouterr()
    assert "pkg-a fedora-43" in captured.err
    assert "pkg-a fedora-44" in captured.err


def test_report_tags_value_error(capsys):
    """Tags raising ValueError (e.g., JSONDecodeError) yields "?"."""
    def failing_tags(up):
        raise ValueError("invalid JSON")

    entries = {"pkg-a": {"upstream": Upstream("github-releases", r"v(\d+\.\d+\.\d+)", repo="x"),
                         "debian": "pkg-a", "fedora": "pkg-a"}}
    rows = report(entries, tags=failing_tags,
                  deb=lambda pkg: {"trixie": "1.0.0", "trixie-backports": "1.0.0"},
                  fed=lambda pkg, rel: "1.0.0")

    assert rows[0]["upstream"] == "?"

    captured = capsys.readouterr()
    assert "pkg-a upstream" in captured.err


def test_report_tags_key_error(capsys):
    """Tags raising KeyError also yields "?"."""
    def failing_tags(up):
        raise KeyError("missing key")

    entries = {"pkg-a": {"upstream": Upstream("github-releases", r"v(\d+\.\d+\.\d+)", repo="x"),
                         "debian": "pkg-a", "fedora": "pkg-a"}}
    rows = report(entries, tags=failing_tags,
                  deb=lambda pkg: {"trixie": "1.0.0", "trixie-backports": "1.0.0"},
                  fed=lambda pkg, rel: "1.0.0")

    assert rows[0]["upstream"] == "?"

    captured = capsys.readouterr()
    assert "pkg-a upstream" in captured.err
