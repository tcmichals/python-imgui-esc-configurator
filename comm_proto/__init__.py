"""Simple common communication protocol for imgui and bridge apps.

Message format (payload returned by pack_message):
- 1 byte: command (0-255)
- 1 byte: content type (1=raw bytes, 2=utf8 string, 3=json)
- 4 bytes: payload length (big-endian unsigned int)
- N bytes: payload

Top-level TCP framing (if used) should still prefix the whole message with
its own 4-byte length as the transport layer expects.
"""
from dataclasses import dataclass
from enum import IntEnum
from typing import Tuple, Union
import struct
import json

from .tang9k_stream import (
    Tang9kChannel,
    Tang9kFrame,
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
from .fcsp import (
    FCSP_CAP_TLV_DSHOT_MOTOR_COUNT,
    FCSP_CAP_TLV_FEATURE_FLAGS,
    FCSP_CAP_TLV_LED_COUNT,
    FCSP_CAP_TLV_MAX_READ_BLOCK_LEN,
    FCSP_CAP_TLV_MAX_WRITE_BLOCK_LEN,
    FCSP_CAP_TLV_NEOPIXEL_COUNT,
    FCSP_CAP_TLV_PROFILE_STRING,
    FCSP_CAP_TLV_PWM_CHANNEL_COUNT,
    FCSP_CAP_TLV_SUPPORTED_IO_SPACES,
    FCSP_CAP_TLV_SUPPORTED_OPS,
    FCSP_CAP_TLV_SUPPORTED_SPACES,
    FCSP_HELLO_TLV_ENDPOINT_NAME,
    FCSP_HELLO_TLV_ENDPOINT_ROLE,
    FCSP_HELLO_TLV_INSTANCE_ID,
    FCSP_HELLO_TLV_PROFILE_STRING,
    FCSP_HELLO_TLV_PROTOCOL_STRING,
    FCSP_HELLO_TLV_UPTIME_MS,
    FcspAddressSpace,
    FcspCapabilitySummary,
    FcspChannel,
    FcspControlOp,
    FcspEndpointRole,
    FcspFlag,
    FcspFrame,
    FcspHelloSummary,
    FcspResult,
    FcspStreamParser,
    FcspTlv,
    build_get_caps_request_payload,
    build_get_caps_response_payload,
    build_hello_payload,
    build_hello_response_payload,
    build_read_block_payload,
    build_control_payload,
    build_write_block_payload,
    decode_frame as decode_fcsp_frame,
    decode_tlvs,
    encode_frame as encode_fcsp_frame,
    encode_tlvs,
    format_capability_tlv,
    parse_get_caps_request_payload,
    parse_get_caps_response_payload,
    parse_hello_payload,
    parse_hello_response_payload,
    parse_read_block_payload,
    parse_control_payload,
    parse_write_block_payload,
    summarize_hello_tlvs,
    summarize_capability_tlvs,
)


class ContentType(IntEnum):
    RAW = 1
    TEXT = 2
    JSON = 3


class Cmd(IntEnum):
    SPI_TRANSFER = 1
    LOG_MESSAGE = 2
    RESET = 3
    SET_DSHOT = 4
    PING = 100


@dataclass
class Message:
    command: int
    content_type: int
    payload: bytes


def pack_message(msg: Message) -> bytes:
    payload_len = len(msg.payload) if msg.payload is not None else 0
    header = struct.pack('>BBI', msg.command & 0xFF, msg.content_type & 0xFF, payload_len)
    return header + (msg.payload or b'')


def unpack_message(data: bytes) -> Message:
    if len(data) < 6:
        raise ValueError('data too short for message')
    cmd, ctype, plen = struct.unpack('>BBI', data[:6])
    payload = data[6:6+plen]
    if len(payload) != plen:
        raise ValueError('payload length mismatch')
    return Message(command=cmd, content_type=ctype, payload=payload)


def make_text_message(command: Cmd, text: str) -> Message:
    return Message(command=command, content_type=ContentType.TEXT, payload=text.encode('utf-8'))


def make_json_message(command: Cmd, obj) -> Message:
    return Message(command=command, content_type=ContentType.JSON, payload=json.dumps(obj).encode('utf-8'))


def decode_payload(msg: Message) -> Union[bytes, str, object]:
    if msg.content_type == ContentType.RAW:
        return msg.payload
    if msg.content_type == ContentType.TEXT:
        return msg.payload.decode('utf-8')
    if msg.content_type == ContentType.JSON:
        return json.loads(msg.payload.decode('utf-8'))
    return msg.payload
