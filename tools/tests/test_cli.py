import argparse
import urllib.error

from conftest import app, write_recipe

from emcomm_build.cli import cmd_check


def test_cmd_check_continues_on_list_tags_failure(fake_repo, monkeypatch, capsys):
    """Test that cmd_check continues after one recipe's list_tags fails."""
    # Create recipes with upstream config (note: app() includes 4-space indent)
    hamlib_recipe = (
        app("hamlib") +
        "    upstream:\n"
        "      type: github-releases\n"
        "      tag_pattern: v(.*)\n"
        "      repo: Hamlib/Hamlib\n"
    )
    wsjtx_recipe = (
        app("wsjtx") +
        "    upstream:\n"
        "      type: github-releases\n"
        "      tag_pattern: v(.*)\n"
        "      repo: wsjtx/wsjtx\n"
    )
    write_recipe(fake_repo, "hamlib", hamlib_recipe)
    write_recipe(fake_repo, "wsjtx", wsjtx_recipe)

    call_count = [0]

    def fake_list_tags(up):
        call_count[0] += 1
        if call_count[0] == 1:
            raise urllib.error.URLError("network error")
        return []

    monkeypatch.setattr("emcomm_build.cli.list_tags", fake_list_tags)

    args = argparse.Namespace(write=False)
    result = cmd_check(args)

    # Should return 1 because one recipe failed
    assert result == 1
    # Should have called list_tags twice (once for each recipe with upstream)
    assert call_count[0] == 2

    # Check stderr output
    captured = capsys.readouterr()
    assert "error:" in captured.err


def _build_args(**kw):
    base = {"target": "debian-13", "arch": None, "out": None, "work": None, "repo_url": None,
            "channel": "testing", "only": [], "force": False, "no_smoke": True}
    base.update(kw)
    return argparse.Namespace(**base)


def test_cmd_build_only_filters_by_target(fake_repo, monkeypatch, capsys):
    import pytest

    from emcomm_build import cli
    from emcomm_build.model import DefinitionError

    write_recipe(fake_repo, "hamlib", app("hamlib"))
    write_recipe(fake_repo, "fedonly", app("fedonly") + "    families: [fedora]\n")
    monkeypatch.setattr(cli, "repo_root", lambda: fake_repo)
    monkeypatch.setattr(cli, "host_arch", lambda: "amd64")
    seen = []
    monkeypatch.setattr(cli, "run_builds", lambda s: seen.append(s.only) or [])

    assert cli.cmd_build(_build_args(only=["fedonly"])) == 0
    assert "skipping fedonly: not built for debian-13" in capsys.readouterr().out
    assert seen == []

    assert cli.cmd_build(_build_args(only=["fedonly", "hamlib"])) == 0
    assert seen == [("hamlib",)]

    with pytest.raises(DefinitionError, match="unknown recipe"):
        cli.cmd_build(_build_args(only=["nope"]))
