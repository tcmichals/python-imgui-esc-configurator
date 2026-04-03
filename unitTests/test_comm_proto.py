from comm_proto import pack_message, unpack_message, make_text_message, make_json_message, decode_payload, Cmd


def test_pack_unpack_text():
    msg = make_text_message(Cmd.LOG_MESSAGE, "hello")
    data = pack_message(msg)
    out = unpack_message(data)
    assert out.command == msg.command
    assert out.content_type == msg.content_type
    assert decode_payload(out) == "hello"


def test_pack_unpack_json():
    msg = make_json_message(Cmd.SET_DSHOT, {"mode": 150})
    data = pack_message(msg)
    out = unpack_message(data)
    assert out.command == msg.command
    assert decode_payload(out) == {"mode": 150}
