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
