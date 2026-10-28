"""Frame format for a length-prefixed, CRC-16 protected serial link.

The wire format is deliberately boring, because boring is what survives a noisy UART:

    | 0x7E | LEN (1 byte) | PAYLOAD (LEN bytes) | CRC-16/CCITT (2 bytes, little endian) |

``0x7E`` is the HDLC-style flag byte. A decoder that loses sync has to hunt for the next flag
and then *prove* the candidate frame with its checksum before trusting it - which is exactly what
this module measures.
"""

from __future__ import annotations

from dataclasses import dataclass

FLAG = 0x7E
HEADER_SIZE = 2
CRC_SIZE = 2
MAX_PAYLOAD = 255


class FrameError(ValueError):
    """Raised when a frame cannot be built."""


def crc16_ccitt(data: bytes, initial: int = 0xFFFF) -> int:
    """CRC-16/CCITT-FALSE: poly 0x1021, init 0xFFFF, no reflection, no final xor."""
    crc = initial
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def encode(payload: bytes) -> bytes:
    """Build one frame around ``payload``."""
    if len(payload) > MAX_PAYLOAD:
        raise FrameError(
            f"payload of {len(payload)} bytes exceeds the {MAX_PAYLOAD}-byte length field"
        )
    body = bytes([FLAG, len(payload)]) + payload
    crc = crc16_ccitt(body)
    return body + bytes([crc & 0xFF, (crc >> 8) & 0xFF])


def encode_many(payloads: list[bytes]) -> bytes:
    return b"".join(encode(payload) for payload in payloads)


@dataclass(frozen=True)
class Frame:
    payload: bytes
    start: int
    end: int

    @property
    def size(self) -> int:
        return self.end - self.start


@dataclass(frozen=True)
class DecodeResult:
    frames: tuple[Frame, ...]
    rejected: int
    bytes_scanned: int
    resync_events: tuple[tuple[int, int], ...] = ()

    @property
    def payloads(self) -> tuple[bytes, ...]:
        return tuple(frame.payload for frame in self.frames)

    @property
    def bytes_to_first_frame(self) -> int:
        return self.frames[0].start if self.frames else self.bytes_scanned


def _candidate_at(stream: bytes, index: int) -> Frame | None:
    """Try to read one whole, checksum-valid frame starting at ``index``."""
    if index + HEADER_SIZE > len(stream) or stream[index] != FLAG:
        return None
    length = stream[index + 1]
    end = index + HEADER_SIZE + length + CRC_SIZE
    if end > len(stream):
        return None
    body = stream[index : index + HEADER_SIZE + length]
    expected = crc16_ccitt(body)
    actual = stream[end - 2] | (stream[end - 1] << 8)
    if expected != actual:
        return None
    return Frame(payload=stream[index + HEADER_SIZE : index + HEADER_SIZE + length],
                 start=index, end=end)


def decode(stream: bytes) -> DecodeResult:
    """Decode every checksum-valid frame, hunting for flags after every rejection.

    A rejected candidate is not assumed to be garbage: the scanner advances one byte and tries
    again, which is how real firmware recovers when a payload happens to contain the flag byte.
    """
    frames: list[Frame] = []
    rejected = 0
    resyncs: list[tuple[int, int]] = []
    index = 0
    while index < len(stream):
        frame = _candidate_at(stream, index)
        if frame is not None:
            frames.append(frame)
            index = frame.end
            continue
        if stream[index] == FLAG:
            rejected += 1
            if frames:
                resyncs.append((index, 1))
            else:
                resyncs.append((index, 1))
        index += 1
    return DecodeResult(
        frames=tuple(frames),
        rejected=rejected,
        bytes_scanned=len(stream),
        resync_events=tuple(resyncs),
    )


def decode_windows(stream: bytes, window: int = 8) -> DecodeResult:
    """Same as :func:`decode` but only ever looks ``window`` bytes ahead.

    A firmware decoder cannot buffer an unbounded stream, so in practice it keeps a small ring
    buffer. Anything that needs more than ``window`` bytes is lost, and that difference is what
    the ``window`` experiment in the README measures.
    """
    frames: list[Frame] = []
    rejected = 0
    resyncs: list[tuple[int, int]] = []
    index = 0
    while index < len(stream):
        chunk = stream[index : index + window]
        frame = _candidate_at(chunk, 0)
        if frame is not None:
            frames.append(
                Frame(payload=frame.payload, start=index, end=index + frame.size)
            )
            index += frame.size
            continue
        if chunk and chunk[0] == FLAG:
            rejected += 1
            resyncs.append((index, 1))
        index += 1
    return DecodeResult(
        frames=tuple(frames),
        rejected=rejected,
        bytes_scanned=len(stream),
        resync_events=tuple(resyncs),
    )
