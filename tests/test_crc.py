from sender.crc import crc16_ccitt


def test_standard_vector():
    assert crc16_ccitt(b"123456789") == 0x29B1


def test_empty_input():
    assert crc16_ccitt(b"") == 0xFFFF


def test_single_byte():
    assert isinstance(crc16_ccitt(b"\x00"), int)


def test_result_is_16bit():
    for data in [b"hello", b"\xff\xff", b"123456789"]:
        result = crc16_ccitt(data)
        assert 0 <= result <= 0xFFFF
