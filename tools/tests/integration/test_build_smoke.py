import shutil

import pytest

from emcomm_build.build import BuildSettings, host_arch, run
from emcomm_build.model import load_targets

from .test_container_build import hello_repo  # noqa: F401  (fixture)

pytestmark = [pytest.mark.container, pytest.mark.nfpm]


@pytest.mark.parametrize("target", ["debian-13", "fedora-44"])
def test_build_package_and_smoke(hello_repo, tmp_path, target):  # noqa: F811
    if shutil.which("nfpm") is None:
        pytest.skip("nfpm not installed")
    settings = BuildSettings(root=hello_repo, target=load_targets(hello_repo)[target],
                             arch=host_arch(), out=tmp_path / "dist", work=tmp_path / "work",
                             repo_url=None)
    built = run(settings)
    assert len(built) == 1 and built[0].exists()
