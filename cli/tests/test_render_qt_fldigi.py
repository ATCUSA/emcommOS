from pathlib import Path

import pytest

from emcomm.models import Operator, RadioDef, Station, UsbMatch
from emcomm.render.context import RenderContext
from emcomm.render.fldigi import render_fldigi
from emcomm.render.ini import set_ini_keys
from emcomm.render.qtini import PTT_VARIANT, render_wsjtx
from emcomm.render.xml import set_xml_elements

FIX = Path(__file__).parent / "fixtures"
IC7300 = RadioDef(id="icom-ic7300", vendor="Icom", model="IC-7300", hamlib_model=3073,
                  baud=19200, ptt="cat")
VOX = RadioDef(id="generic-vox", vendor="Generic", model="VOX", hamlib_model=1, baud=9600,
               ptt="vox")
OP = Operator(callsign="K7ABC", name="Pat Q", grid="DN16bk")
KIT = Station(name="kita", radio="icom-ic7300", cat=UsbMatch("10c4", "ea60"),
              audio=UsbMatch("08bb", "2901"))


def ctx(radio=IC7300, station=KIT, op=OP):
    return RenderContext(operator=op, station=station, radio=radio)


def test_set_ini_keys_preserves_other_lines():
    original = (FIX / "WSJT-X.ini").read_text()
    out = set_ini_keys(original, "Configuration", {"MyCall": "K7ABC", "MyGrid": "DN16bk"})
    # Exact output assertion: verify exact byte-for-byte match
    assert out == (
        "[Common]\n"
        "Mode=FT8\n"
        "NDepth=3\n"
        "\n"
        "[Configuration]\n"
        "MyCall=K7ABC\n"
        "Font=\"Sans Serif,10,-1,5,50,0,0,0,0,0\"\n"
        "Rig=None\n"
        "PTTMethod=@Variant(\\0\\0\\0\\x7f\\0\\0\\0\\x1eTransceiverFactory::PTTMethod\\0\\0\\0\\0\\xfPTT_method_VOX\\0)\n"
        "SoundInName=default\n"
        "DecodeAtStartup=true\n"
        "MyGrid=DN16bk\n"
        "\n"
        "[MainWindow]\n"
        "geometry=@ByteArray(\\x1\\xd9\\xd0\\xcb)\n"
    )


def test_set_ini_keys_creates_section_and_file():
    assert set_ini_keys("", "Configuration", {"A": "1"}) == "[Configuration]\nA=1\n"
    assert set_ini_keys("[X]\nk=v", "Configuration", {"A": "1"}) == "[X]\nk=v\n\n[Configuration]\nA=1\n"


def test_set_ini_keys_unicode_separator_in_unmanaged_value():
    # Unicode line separator (U+2028) in an unmanaged value should be preserved exactly
    text = "[Config]\nUnmanaged=value\u2028here\n"
    out = set_ini_keys(text, "Config", {"Managed": "new"})
    assert "value\u2028here" in out
    assert out == "[Config]\nUnmanaged=value\u2028here\nManaged=new\n"


def test_set_ini_keys_crlf_file_stays_crlf():
    # CRLF file should stay CRLF including appended keys
    text = "[Config]\r\nKey1=val1\r\n"
    out = set_ini_keys(text, "Config", {"Key2": "val2"})
    assert out == "[Config]\r\nKey1=val1\r\nKey2=val2\r\n"


def test_set_ini_keys_bom_and_header_on_first_line():
    # BOM + section header on first line should update in place, no duplicate section
    text = "\ufeff[Config]\nKey1=val1\n"
    out = set_ini_keys(text, "Config", {"Key1": "new1", "Key2": "new2"})
    assert out == "\ufeff[Config]\nKey1=new1\nKey2=new2\n"
    # Verify no duplicate [Config] section
    assert out.count("[Config]") == 1


def test_set_ini_keys_duplicate_keys_all_updated():
    # Duplicate keys in section should all be updated
    text = "[Config]\nMyKey=old1\nOther=val\nMyKey=old2\n"
    out = set_ini_keys(text, "Config", {"MyKey": "new"})
    assert out == "[Config]\nMyKey=new\nOther=val\nMyKey=new\n"


def test_set_ini_keys_same_key_other_section_untouched():
    # Same key in another section should be untouched
    text = "[Config1]\nKey=val1\n\n[Config2]\nKey=val2\n"
    out = set_ini_keys(text, "Config1", {"Key": "new"})
    assert "[Config1]\nKey=new\n" in out
    assert "[Config2]\nKey=val2\n" in out


def test_set_ini_keys_rejects_newline_in_value():
    # Values containing \n or \r should be rejected
    with pytest.raises(ValueError, match="must not contain newlines"):
        set_ini_keys("[C]\n", "C", {"K": "val\nue"})
    with pytest.raises(ValueError, match="must not contain newlines"):
        set_ini_keys("[C]\n", "C", {"K": "val\rue"})


def test_wsjtx_render():
    out = render_wsjtx((FIX / "WSJT-X.ini").read_text(), ctx())
    lines = out.splitlines()
    assert "MyCall=K7ABC" in lines
    assert "MyGrid=DN16bk" in lines
    assert "Rig=Hamlib NET rigctl" in lines
    assert "CATNetworkPort=127.0.0.1:4532" in lines
    assert "PTTMethod=" + PTT_VARIANT.format("CAT") in lines
    assert 'SoundInName="sysdefault:CARD=EMCOMM_KITA"' in lines
    assert 'SoundOutName="sysdefault:CARD=EMCOMM_KITA"' in lines
    assert "Mode=FT8" in lines and "geometry=@ByteArray(\\x1\\xd9\\xd0\\xcb)" in lines


def test_wsjtx_vox_and_no_audio():
    out = render_wsjtx(None, ctx(radio=VOX, station=Station(name="bench", radio="generic-vox")))
    assert "PTTMethod=" + PTT_VARIANT.format("VOX") in out.splitlines()
    assert "SoundInName" not in out


def test_variant_literal_is_exact():
    assert PTT_VARIANT.format("CAT") == (
        r"@Variant(\0\0\0\x7f\0\0\0\x1eTransceiverFactory::PTTMethod\0\0\0\0\xfPTT_method_CAT\0)"
    )


def test_set_xml_elements():
    out = set_xml_elements((FIX / "fldigi_def.xml").read_text(), "FLDIGI_DEFS",
                           {"MYCALL": "K7ABC", "MYLOC": "DN16bk", "MYNAME": "A&B"})
    assert "<MYCALL>K7ABC</MYCALL>" in out
    assert "<MYLOC>DN16bk</MYLOC>" in out
    assert "<MYNAME>A&amp;B</MYNAME>" in out
    assert "<WFREFLEVEL>-20</WFREFLEVEL>" in out
    assert out.rstrip().endswith("</FLDIGI_DEFS>")


def test_set_xml_elements_with_attributes():
    # XML element with attributes should be updated with attributes preserved
    text = "<ROOT>\n<TAG attr=\"val\">old</TAG>\n</ROOT>\n"
    out = set_xml_elements(text, "ROOT", {"TAG": "new"})
    assert out == "<ROOT>\n<TAG attr=\"val\">new</TAG>\n</ROOT>\n"


def test_set_xml_elements_self_closing_tag():
    # Self-closing tag should be handled and converted to regular element
    text = "<ROOT>\n<EMPTY attr=\"val\" />\n</ROOT>\n"
    out = set_xml_elements(text, "ROOT", {"EMPTY": "content"})
    # Self-closing tag is converted to regular element, preserving attributes
    assert "<EMPTY attr=\"val\"" in out and ">content</EMPTY>" in out


def test_set_xml_elements_tag_substring():
    # MYCALL vs MYCALLX should not cross-match
    text = "<ROOT>\n<MYCALL>old</MYCALL>\n<MYCALLX>preserve</MYCALLX>\n</ROOT>\n"
    out = set_xml_elements(text, "ROOT", {"MYCALL": "new"})
    assert "<MYCALL>new</MYCALL>" in out
    assert "<MYCALLX>preserve</MYCALLX>" in out


def test_set_xml_elements_backslash_and_ampersand():
    # Backslash and & in values should be properly escaped
    text = "<ROOT>\n<VAL>old</VAL>\n</ROOT>\n"
    out = set_xml_elements(text, "ROOT", {"VAL": "C:\\path & more"})
    assert "<VAL>C:\\path &amp; more</VAL>" in out


def test_set_xml_elements_rejects_newline_in_value():
    # Values containing \n or \r should be rejected
    with pytest.raises(ValueError, match="must not contain newlines"):
        set_xml_elements("<R></R>", "R", {"T": "val\nue"})
    with pytest.raises(ValueError, match="must not contain newlines"):
        set_xml_elements("<R></R>", "R", {"T": "val\rue"})


def test_fldigi_render():
    out = render_fldigi((FIX / "fldigi_def.xml").read_text(), ctx())
    for tag, value in (("MYCALL", "K7ABC"), ("MYLOC", "DN16bk"), ("MYNAME", "Pat Q"),
                       ("CHKUSEHAMLIBIS", "1"), ("HAMRIGMODEL", "2"),
                       ("HAMRIGDEVICE", "127.0.0.1:4532"), ("HAMLIBCMDPTT", "1"),
                       ("CHKUSERIGCATIS", "0"), ("CHKUSEXMLRPCIS", "0")):
        assert f"<{tag}>{value}</{tag}>" in out
    assert "<HAMRIGNAME></HAMRIGNAME>" in out
    assert "<MYQTH>Somewhere</MYQTH>" in out
    vox = render_fldigi(None, ctx(radio=VOX))
    assert "<HAMLIBCMDPTT>0</HAMLIBCMDPTT>" in vox
