import pytest

from emcomm.models import Station, ax25_callsign, normalize_callsign, normalize_grid
from emcomm.paths import Paths


@pytest.mark.parametrize("raw,expected", [("k7abc", "K7ABC"), (" ve7/k7abc ", "VE7/K7ABC"),
                                          ("K7ABC/P", "K7ABC/P"), ("W1AW", "W1AW")])
def test_callsign_ok(raw, expected):
    assert normalize_callsign(raw) == expected


@pytest.mark.parametrize("raw", ["", "KABC", "K7 ABC", "K7ABC!"])
def test_callsign_bad(raw):
    with pytest.raises(ValueError):
        normalize_callsign(raw)


def test_grid():
    assert normalize_grid("dn16BK") == "DN16bk"
    assert normalize_grid("dn16") == "DN16"
    assert normalize_grid("") == ""
    with pytest.raises(ValueError):
        normalize_grid("ZZ99")


def test_ax25_callsign():
    assert ax25_callsign("VE7/K7ABC") == "K7ABC"
    assert ax25_callsign("K7ABC/P") == "K7ABC"
    assert ax25_callsign("VK9/K7A") == "K7A"
    assert ax25_callsign("W1AW") == "W1AW"


def test_station_derived_names():
    st = Station(name="kit-a", radio="icom-ic7300")
    assert st.cat_link == "/dev/emcomm/cat-kit-a"
    assert st.alsa_id == "EMCOMM_KIT_A"


def test_paths_from_env(tmp_path):
    p = Paths.from_env({"EMCOMM_ROOT": str(tmp_path)})
    assert p.stations_dir == tmp_path / "etc/emcomm/stations"
    assert p.operators_dir == tmp_path / "home/.config/emcomm/operators"
    assert p.radios_dir == tmp_path / "opt/emcomm/share/emcomm/radios"
