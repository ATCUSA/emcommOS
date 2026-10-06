import pytest

from emcomm.cli import main
from emcomm.radios import load_radios
from emcomm.validation import ProfileError


def test_repo_radios_load(paths):
    radios = load_radios(paths.radios_dir)
    assert radios["icom-ic7300"].hamlib_model == 3073
    assert radios["icom-ic7300"].cat_hints[0].serial_prefix == "IC-7300"
    assert radios["generic-rts"].ptt == "rts"
    assert len(radios["generic-rts"].audio_hints) == 2


def test_id_must_match_filename(tmp_path):
    (tmp_path / "foo.yaml").write_text(
        "id: bar\nvendor: X\nmodel: Y\nhamlib_model: 1\nbaud: 9600\nptt: vox\n")
    with pytest.raises(ProfileError, match="file name"):
        load_radios(tmp_path)


def test_bad_baud(tmp_path):
    (tmp_path / "foo.yaml").write_text(
        "id: foo\nvendor: X\nmodel: Y\nhamlib_model: 1\nbaud: 1234\nptt: vox\n")
    with pytest.raises(ProfileError, match="baud"):
        load_radios(tmp_path)


def test_radios_command(paths, capsys):
    assert main(["radios"], paths=paths) == 0
    assert "icom-ic7300" in capsys.readouterr().out
    assert main(["radios", "yaesu-ft991a"], paths=paths) == 0
    assert "CAT RATE: 38400" in capsys.readouterr().out
