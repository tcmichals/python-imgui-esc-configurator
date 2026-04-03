from comm_proto.fcsp import (
    FcspChannel,
    FcspControlOp,
    FcspStreamParser,
    FcspTlv,
    build_control_payload,
    decode_frame,
    decode_tlvs,
    encode_frame,
    encode_tlvs,
    parse_control_payload,
)


def test_fcsp_frame_roundtrip() -> None:
    payload = b"abc123"
    raw = encode_frame(FcspChannel.CONTROL, seq=9, payload=payload, flags=0x01)
    frame = decode_frame(raw)
    assert frame.channel == FcspChannel.CONTROL
    assert frame.seq == 9
    assert frame.payload == payload
    assert frame.flags == 0x01


def test_fcsp_stream_parser_recovers_from_noise() -> None:
    good_a = encode_frame(FcspChannel.CONTROL, seq=1, payload=b"A")
    good_b = encode_frame(FcspChannel.FC_LOG, seq=2, payload=b"B")
    parser = FcspStreamParser()
    frames = parser.feed(b"\x00\x01" + good_a + b"\xFF" + good_b)
    assert len(frames) == 2
    assert frames[0].seq == 1
    assert frames[1].seq == 2


def test_fcsp_control_payload_build_parse() -> None:
    body = b"\x01\x02"
    payload = build_control_payload(FcspControlOp.PING, body)
    op_id, rest = parse_control_payload(payload)
    assert op_id == FcspControlOp.PING
    assert rest == body


def test_fcsp_tlv_roundtrip() -> None:
    tlvs = [
        FcspTlv(tlv_type=0x01, value=b"offloader"),
        FcspTlv(tlv_type=0x10, value=(4).to_bytes(2, "big")),
    ]
    raw = encode_tlvs(tlvs)
    decoded = decode_tlvs(raw)
    assert decoded == tlvs
