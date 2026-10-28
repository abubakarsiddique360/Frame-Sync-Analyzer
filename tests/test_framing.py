import pytest

from frame_sync_analyzer.framing import (
    FLAG,
    FrameError,
    crc16_ccitt,
    decode,
    decode_windows,
    encode,
    encode_many,
)

PAYLOADS = [b"TEMP=21.5", b"HUM=48", b"DOOR=open"]


def test_crc_check_value():
    # The standard check value for CRC-16/CCITT-FALSE is 0x29B1 for "123456789".
    assert crc16_ccitt(b"123456789") == 0x29B1


def test_crc_of_empty_is_initial_value():
    assert crc16_ccitt(b"") == 0xFFFF


def test_encode_layout():
    frame = encode(b"AB")
    assert frame[0] == FLAG
    assert frame[1] == 2
    assert frame[2:4] == b"AB"
    assert len(frame) == 2 + 2 + 2


def test_encode_rejects_oversized_payload():
    with pytest.raises(FrameError, match="255-byte length field"):
        encode(b"x" * 256)


def test_roundtrip_of_many_frames():
    stream = encode_many(PAYLOADS)
    result = decode(stream)
    assert result.payloads == tuple(PAYLOADS)
    assert result.rejected == 0


def test_frame_offsets_are_contiguous():
    stream = encode_many(PAYLOADS)
    result = decode(stream)
    assert result.frames[0].start == 0
    for previous, current in zip(result.frames, result.frames[1:], strict=False):
        assert current.start == previous.end


def test_garbage_prefix_is_skipped():
    stream = b"\x01\x02\x03\x7e\x00\x00" + encode_many(PAYLOADS)
    result = decode(stream)
    assert result.payloads == tuple(PAYLOADS)
    assert result.bytes_to_first_frame > 0


def test_truncated_last_frame_is_not_returned():
    stream = encode_many(PAYLOADS)[:-2]
    result = decode(stream)
    assert result.payloads == tuple(PAYLOADS[:2])


def test_corrupted_payload_is_rejected_and_next_frame_found():
    stream = bytearray(encode_many(PAYLOADS))
    stream[3] ^= 0xFF  # corrupt the first payload byte
    result = decode(bytes(stream))
    assert result.payloads == tuple(PAYLOADS[1:])
    assert result.rejected >= 1


def test_spurious_flag_inside_payload_does_not_break_sync():
    payload = bytes([0x7E, 0x41])
    stream = encode(payload) + encode(b"next")
    result = decode(stream)
    assert result.payloads == (payload, b"next")


def test_window_smaller_than_a_frame_sees_nothing():
    stream = encode_many(PAYLOADS)
    assert decode_windows(stream, window=4).payloads == ()


def test_window_large_enough_matches_full_decode():
    stream = encode_many(PAYLOADS)
    assert decode_windows(stream, window=32).payloads == decode(stream).payloads


def test_empty_stream():
    result = decode(b"")
    assert result.frames == ()
    assert result.bytes_scanned == 0
    assert result.bytes_to_first_frame == 0
