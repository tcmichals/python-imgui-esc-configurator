from comm_proto.tang9k_stream import (
    MAX_PAYLOAD_RECOMMENDED,
    Tang9kChannel,
    Tang9kLogEvent,
    Tang9kLogLevel,
    Tang9kLogSource,
    Tang9kStreamParser,
    decode_fc_log_event,
    decode_frame,
    encode_fc_log_event,
    encode_frame,
    format_fc_log_event,
    format_frame_trace,
)


def test_encode_decode_frame_roundtrip():
    payload = bytes.fromhex("01 02 AA BB")
    frame_bytes = encode_frame(Tang9kChannel.FC_LOG, seq=42, payload=payload, flags=0x01)
    frame = decode_frame(frame_bytes)

    assert frame.version == 1
    assert frame.channel == Tang9kChannel.FC_LOG
    assert frame.seq == 42
    assert frame.flags == 0x01
    assert frame.payload == payload


def test_encode_frame_rejects_payload_too_large():
    too_big = b"A" * 0x10000
    try:
        encode_frame(Tang9kChannel.CONTROL, seq=1, payload=too_big)
    except ValueError as exc:
        assert "payload too large" in str(exc)
    else:
        raise AssertionError("expected payload too large")


def test_parser_resyncs_and_decodes_after_corruption():
    valid_a = encode_frame(Tang9kChannel.CONTROL, seq=5, payload=b"abc")
    valid_b = encode_frame(Tang9kChannel.FC_LOG, seq=6, payload=b"xyz")

    parser = Tang9kStreamParser(max_payload=MAX_PAYLOAD_RECOMMENDED)
    # Include junk + partial frame to force sync search and partial buffering.
    first_chunk = b"\x00\x11\x22" + valid_a[:7]
    second_chunk = valid_a[7:] + b"\xFF\xFE" + valid_b

    out1 = parser.feed(first_chunk)
    out2 = parser.feed(second_chunk)

    assert out1 == []
    assert [f.seq for f in out2] == [5, 6]
    assert [bytes(f.payload) for f in out2] == [b"abc", b"xyz"]


def test_fc_log_event_roundtrip_and_format():
    event = Tang9kLogEvent(
        level=Tang9kLogLevel.WARN,
        source=Tang9kLogSource.FC,
        uptime_ms=1234,
        message="rpm saturation",
    )

    payload = encode_fc_log_event(event)
    decoded = decode_fc_log_event(payload)
    text = format_fc_log_event(decoded)

    assert decoded.level == Tang9kLogLevel.WARN
    assert decoded.source == Tang9kLogSource.FC
    assert decoded.uptime_ms == 1234
    assert decoded.message == "rpm saturation"
    assert "FC/WARN" in text
    assert "+1234ms" in text


def test_format_frame_trace_contains_channel_seq_and_hex():
    frame_bytes = encode_frame(Tang9kChannel.DEBUG_TRACE, seq=99, payload=b"\x10\x20")
    trace = format_frame_trace("->", frame_bytes)
    assert "TANG9K ->" in trace
    assert "CH=DEBUG_TRACE" in trace
    assert "SEQ=99" in trace
    assert frame_bytes.hex(" ").upper() in trace
