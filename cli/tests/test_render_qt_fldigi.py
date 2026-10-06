from pathlib import Path

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
    assert "MyCall=K7ABC\n" in out
    # new keys are appended at the end of the section, before the blank separator line
    assert "DecodeAtStartup=true\nMyGrid=DN16bk\n\n[MainWindow]" in out
    for line in original.splitlines():
        if not line.startswith("MyCall="):
            assert line in out.splitlines()


def test_set_ini_keys_creates_section_and_file():
    assert set_ini_keys("", "Configuration", {"A": "1"}) == "[Configuration]\nA=1\n"
    assert set_ini_keys("[X]\nk=v", "Configuration", {"A": "1"}) == "[X]\nk=v\n\n[Configuration]\nA=1\n"


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
