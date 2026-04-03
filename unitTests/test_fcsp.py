from comm_proto.fcsp import (
    FCSP_CAP_TLV_DSHOT_MOTOR_COUNT,
    FCSP_CAP_TLV_FEATURE_FLAGS,
    FCSP_CAP_TLV_MAX_READ_BLOCK_LEN,
    FCSP_CAP_TLV_PROFILE_STRING,
    FCSP_HELLO_TLV_ENDPOINT_NAME,
    FCSP_HELLO_TLV_ENDPOINT_ROLE,
    FCSP_HELLO_TLV_PROTOCOL_STRING,
    FcspAddressSpace,
    FcspCapabilitySummary,
    FcspChannel,
    FcspControlOp,
    FcspEndpointRole,
    FcspHelloSummary,
    FcspStreamParser,
    FcspTlv,
    build_get_caps_response_payload,
    build_hello_payload,
    build_hello_response_payload,
    build_read_block_payload,
    build_control_payload,
    build_write_block_payload,
    decode_frame,
    decode_tlvs,
    encode_frame,
    encode_tlvs,
    format_capability_tlv,
    parse_get_caps_response_payload,
    parse_hello_payload,
    parse_hello_response_payload,
    parse_read_block_payload,
    parse_control_payload,
    parse_write_block_payload,
    summarize_hello_tlvs,
    summarize_capability_tlvs,
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


def test_fcsp_capability_summary_decodes_known_tlvs() -> None:
    tlvs = [
        FcspTlv(tlv_type=FCSP_CAP_TLV_DSHOT_MOTOR_COUNT, value=b"\x00\x04"),
        FcspTlv(tlv_type=FCSP_CAP_TLV_MAX_READ_BLOCK_LEN, value=b"\x01\x00"),
        FcspTlv(tlv_type=FCSP_CAP_TLV_PROFILE_STRING, value=b"SERV8-50-SPIPROD"),
        FcspTlv(tlv_type=FCSP_CAP_TLV_FEATURE_FLAGS, value=b"\x00\x00\x00\x01"),
    ]

    summary = summarize_capability_tlvs(tlvs)

    assert summary == FcspCapabilitySummary(
        supported_ops_bitmap=None,
        supported_spaces_bitmap=None,
        max_read_block_length=256,
        max_write_block_length=None,
        profile_string="SERV8-50-SPIPROD",
        feature_flags=1,
        pwm_channel_count=None,
        dshot_motor_count=4,
        led_count=None,
        neopixel_count=None,
        supported_io_spaces_bitmap=None,
        entries=tuple(tlvs),
    )
    assert format_capability_tlv(tlvs[0]) == "DSHOT motor count: 4"
    assert format_capability_tlv(tlvs[1]) == "Max read block length: 256"
    assert format_capability_tlv(tlvs[2]) == "Profile string: SERV8-50-SPIPROD"
    assert format_capability_tlv(tlvs[3]) == "Feature flags: 0x00000001"


def test_fcsp_hello_payload_roundtrip() -> None:
    tlvs = [
        FcspTlv(tlv_type=FCSP_HELLO_TLV_ENDPOINT_ROLE, value=bytes([FcspEndpointRole.OFFLOADER])),
        FcspTlv(tlv_type=FCSP_HELLO_TLV_ENDPOINT_NAME, value=b"fcsp-offloader-01"),
        FcspTlv(tlv_type=FCSP_HELLO_TLV_PROTOCOL_STRING, value=b"FCSP/1"),
    ]

    raw = build_hello_payload(tlvs)
    decoded = parse_hello_payload(raw)
    summary = summarize_hello_tlvs(decoded)

    assert decoded == tlvs
    assert summary == FcspHelloSummary(
        endpoint_role=FcspEndpointRole.OFFLOADER,
        endpoint_name="fcsp-offloader-01",
        protocol_string="FCSP/1",
        profile_string="",
        instance_id=None,
        uptime_ms=None,
        entries=tuple(tlvs),
    )


def test_fcsp_hello_response_payload_roundtrip() -> None:
    tlvs = [FcspTlv(tlv_type=FCSP_HELLO_TLV_ENDPOINT_NAME, value=b"offloader")]

    raw = build_hello_response_payload(0, tlvs)
    result, decoded = parse_hello_response_payload(raw)

    assert result == 0
    assert decoded == tlvs


def test_fcsp_get_caps_response_payload_roundtrip() -> None:
    tlvs = [
        FcspTlv(tlv_type=FCSP_CAP_TLV_DSHOT_MOTOR_COUNT, value=b"\x00\x04"),
        FcspTlv(tlv_type=FCSP_CAP_TLV_FEATURE_FLAGS, value=b"\x00\x00\x00\x01"),
    ]

    raw = build_get_caps_response_payload(0, tlvs)
    result, decoded, page, has_more = parse_get_caps_response_payload(raw)

    assert result == 0
    assert decoded == tlvs
    assert page is None
    assert has_more is None


def test_fcsp_read_write_block_payload_roundtrip() -> None:
    read_payload = build_read_block_payload(FcspAddressSpace.ESC_EEPROM, 0x1234, 16)
    assert parse_read_block_payload(read_payload) == (FcspAddressSpace.ESC_EEPROM, 0x1234, 16)

    write_payload = build_write_block_payload(FcspAddressSpace.FLASH, 0x2000, b"\xAA\x55")
    assert parse_write_block_payload(write_payload) == (FcspAddressSpace.FLASH, 0x2000, b"\xAA\x55")
