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
