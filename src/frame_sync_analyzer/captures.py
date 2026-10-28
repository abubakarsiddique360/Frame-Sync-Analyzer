"""Generate serial captures with the kinds of damage a real link produces."""

from __future__ import annotations

import random
from dataclasses import dataclass

from .framing import FLAG, encode


@dataclass(frozen=True)
class Capture:
    name: str
    stream: bytes
    expected: tuple[bytes, ...]
    damage: tuple[str, ...] = ()


def clean(payloads: list[bytes], *, seed: int = 0) -> Capture:
    return Capture(name="clean", stream=b"".join(encode(p) for p in payloads),
                   expected=tuple(payloads))


def line_noise(payloads: list[bytes], *, flip_rate: float = 0.008, seed: int = 11) -> Capture:
    """Flip random bits, as a marginal cable does."""
    rng = random.Random(seed)
    stream = bytearray(b"".join(encode(p) for p in payloads))
    flips = 0
    for index in range(len(stream)):
        if rng.random() < flip_rate:
            stream[index] ^= 1 << rng.randrange(8)
            flips += 1
    return Capture(name="line noise", stream=bytes(stream), expected=tuple(payloads),
                   damage=("bitflips", f"{flips} bits"))


def dropped_bytes(payloads: list[bytes], *, drop: int = 3, at: int = 40, seed: int = 1) -> Capture:
    """Lose a few bytes mid-stream, which shifts every later frame boundary."""
    stream = b"".join(encode(p) for p in payloads)
    damaged = stream[:at] + stream[at + drop :]
    return Capture(name="dropped bytes", stream=damaged, expected=tuple(payloads),
                   damage=("truncation", f"{drop} bytes"))


def stuck_flag(payloads: list[bytes], *, count: int = 5, at: int = 30, seed: int = 2) -> Capture:
    """A line that idles high injects spurious flag bytes."""
    stream = b"".join(encode(p) for p in payloads)
    damaged = stream[:at] + bytes([FLAG] * count) + stream[at:]
    return Capture(name="stuck flag", stream=damaged, expected=tuple(payloads),
                   damage=("spurious flags", str(count)))


def garbage_prefix(payloads: list[bytes], *, length: int = 17, seed: int = 3) -> Capture:
    """The receiver boots late and catches the tail of the previous session."""
    rng = random.Random(seed)
    prefix = bytes(rng.randrange(1, 255) for _ in range(length))
    return Capture(name="garbage prefix", stream=prefix + b"".join(encode(p) for p in payloads),
                   expected=tuple(payloads), damage=("cold start", f"{length} bytes"))


SCENARIOS = {
    "clean": clean,
    "line noise": line_noise,
    "dropped bytes": dropped_bytes,
    "stuck flag": stuck_flag,
    "garbage prefix": garbage_prefix,
}
