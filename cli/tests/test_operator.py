from emcomm.cli import main


def test_add_list_show(paths, capsys):
    assert main(["operator", "add", "k7abc", "--name", "Pat Q", "--grid", "dn16bk"],
                paths=paths) == 0
    assert (paths.operators_dir / "k7abc.toml").is_file()
    assert main(["operator", "list"], paths=paths) == 0
    assert "K7ABC" in capsys.readouterr().out
    assert main(["operator", "show", "K7ABC"], paths=paths) == 0
    out = capsys.readouterr().out
    assert "grid: DN16bk" in out and "name: Pat Q" in out


def test_portable_callsign_file_name(paths):
    assert main(["operator", "add", "VE7/K7ABC"], paths=paths) == 0
    assert (paths.operators_dir / "ve7_k7abc.toml").is_file()


def test_invalid_callsign(paths, capsys):
    assert main(["operator", "add", "nope"], paths=paths) == 1
    assert "invalid callsign" in capsys.readouterr().err


def test_show_missing(paths, capsys):
    assert main(["operator", "show", "K7ZZZ"], paths=paths) == 1
    assert "emcomm operator add" in capsys.readouterr().err


def test_list_empty(paths, capsys):
    assert main(["operator", "list"], paths=paths) == 0
    assert "no operators yet" in capsys.readouterr().out
