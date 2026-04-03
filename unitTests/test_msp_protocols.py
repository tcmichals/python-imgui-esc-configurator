from MSP.fourway import (
    FOURWAY_ACK,
    FOURWAY_FC_SYNC,
    FOURWAY_CMDS,
    build_fourway_frame,
    crc16_xmodem,
    parse_fourway_response_frame,
)
from MSP.protocol import (
    MSP_HEADER_IN,
    MSP_HEADER_OUT,
    build_msp_frame,
    calc_checksum,
    parse_msp_frame,
)


def test_build_and_parse_msp_frame_roundtrip():
    payload = bytes.fromhex("01ff23")
    frame = build_msp_frame(245, payload, header=MSP_HEADER_OUT)
    parsed = parse_msp_frame(frame)

    assert parsed.header == MSP_HEADER_OUT
    assert parsed.command == 245
    assert parsed.payload == payload
    assert parsed.size == len(payload)


def test_parse_msp_response_frame_roundtrip():
    payload = b"\x04\x00"
    frame = build_msp_frame(245, payload, header=MSP_HEADER_IN)
    parsed = parse_msp_frame(frame)

    assert parsed.is_response
    assert not parsed.is_error
    assert parsed.payload == payload


def test_parse_msp_frame_rejects_bad_checksum():
    frame = bytearray(build_msp_frame(105, b"\x01\x02"))
    frame[-1] ^= 0xFF

    try:
        parse_msp_frame(bytes(frame))
    except ValueError as exc:
        assert "checksum mismatch" in str(exc)
    else:
        raise AssertionError("expected checksum mismatch")


def test_build_fourway_frame_includes_crc():
    frame = build_fourway_frame(FOURWAY_CMDS["test_alive"])
    body = frame[:-2]
    crc = (frame[-2] << 8) | frame[-1]

    assert frame[0] == 0x2F
    assert crc == crc16_xmodem(body)


def test_parse_fourway_response_roundtrip():
    params = b"BLHeli_32"
    param_len = len(params)
    ack = 0x00
    body = bytes([
        FOURWAY_FC_SYNC,
        FOURWAY_CMDS["get_name"],
        0x00,
        0x10,
        param_len,
    ]) + params + bytes([ack])
    crc = crc16_xmodem(body)
    frame = body + bytes([(crc >> 8) & 0xFF, crc & 0xFF])

    parsed = parse_fourway_response_frame(frame)
    assert parsed.command == FOURWAY_CMDS["get_name"]
    assert parsed.address == 0x0010
    assert parsed.params == params
    assert parsed.ack == ack
    assert parsed.ack_str == FOURWAY_ACK[ack]
    assert parsed.crc_ok is True


def test_parse_fourway_response_flags_bad_crc():
    params = b"\x01\x02"
    body = bytes([
        FOURWAY_FC_SYNC,
        FOURWAY_CMDS["read"],
        0x00,
        0x20,
        len(params),
    ]) + params + b"\x00"
    crc = crc16_xmodem(body) ^ 0xFFFF
    frame = body + bytes([(crc >> 8) & 0xFF, crc & 0xFF])

    parsed = parse_fourway_response_frame(frame)
    assert parsed.crc_ok is False
