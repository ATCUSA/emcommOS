import pytest

from emcomm.validation import ProfileError, validate


def test_station_name_rejects_newline():
    """Station name with newline should be rejected."""
    data = {"name": "kit-a\n", "radio": "test"}
    with pytest.raises(ProfileError):
        validate("station", data, "test")


def test_serial_rejects_newline():
    """Serial with embedded newline should be rejected."""
    data = {
        "name": "kit-a",
        "radio": "test",
        "cat": {"vendor_id": "10c4", "product_id": "ea60", "serial": "X\nY"},
    }
    with pytest.raises(ProfileError):
        validate("station", data, "test")


def test_serial_rejects_quote():
    """Serial with quote should be rejected."""
    data = {
        "name": "kit-a",
        "radio": "test",
        "cat": {"vendor_id": "10c4", "product_id": "ea60", "serial": 'a"b'},
    }
    with pytest.raises(ProfileError):
        validate("station", data, "test")


def test_serial_accepts_normal():
    """Normal serial should be accepted."""
    data = {
        "name": "kit-a",
        "radio": "test",
        "cat": {"vendor_id": "10c4", "product_id": "ea60", "serial": "IC-7300 03001234 A"},
    }
    validate("station", data, "test")


def test_vendor_id_rejects_newline():
    """Vendor ID with newline should be rejected."""
    data = {
        "name": "kit-a",
        "radio": "test",
        "cat": {"vendor_id": "10c4\n", "product_id": "ea60"},
    }
    with pytest.raises(ProfileError):
        validate("station", data, "test")


def test_station_name_9_char_rejects():
    """Station name with 9 characters should be rejected (max 8)."""
    data = {"name": "kit-abcd9", "radio": "test"}
    with pytest.raises(ProfileError):
        validate("station", data, "test")


def test_station_name_8_char_accepts():
    """Station name with 8 characters should be accepted."""
    data = {"name": "kit-abcd", "radio": "test"}
    validate("station", data, "test")
