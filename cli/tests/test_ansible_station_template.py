import tomllib
from pathlib import Path

import jinja2

from emcomm.profiles import station_from_dict

TEMPLATE = (Path(__file__).resolve().parents[2] / "ansible/ansible_collections/emcomm/station"
            / "roles/radio_hw/templates/station.toml.j2")


def render(item):
    env = jinja2.Environment(trim_blocks=True)  # Ansible's template module default
    return env.from_string(TEMPLATE.read_text()).render(item=item)


def test_template_round_trips():
    item = {"name": "kita", "radio": "icom-ic7300", "ptt": "cat",
            "cat": {"vendor_id": "10c4", "product_id": "ea60", "serial": "IC-7300 0300 A",
                    "interface": "00"},
            "audio": {"vendor_id": "08bb", "product_id": "2901"}}
    st = station_from_dict(tomllib.loads(render(item)), "test")
    assert st.cat.serial == "IC-7300 0300 A" and st.audio.product_id == "2901"


def test_template_minimal():
    st = station_from_dict(tomllib.loads(render({"name": "b", "radio": "generic-vox"})), "t")
    assert st.cat is None and st.ptt is None


def test_template_control():
    st = station_from_dict(tomllib.loads(render(
        {"name": "mk2", "radio": "icom-ic7300mk2", "control": "wfview"})), "t")
    assert st.control == "wfview"
