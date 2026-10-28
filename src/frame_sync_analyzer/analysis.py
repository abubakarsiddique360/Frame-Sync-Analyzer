"""Turn decode results into measurements: what was recovered, and what it cost."""

from __future__ import annotations

from dataclasses import dataclass

from .captures import Capture
from .framing import DecodeResult, decode, decode_windows


@dataclass(frozen=True)
class Outcome:
    scenario: str
    expected: int
    recovered: int
    correct: int
    rejected_candidates: int
    lost_bytes: int
    first_frame_offset: int
    bytes_scanned: int

    @property
    def recovery(self) -> float:
        return self.recovered / self.expected if self.expected else 0.0

    @property
    def loss(self) -> float:
        return self.lost_bytes / self.bytes_scanned if self.bytes_scanned else 0.0

    def as_dict(self) -> dict:
        return {
            "scenario": self.scenario,
            "expected": self.expected,
            "recovered": self.recovered,
            "correct": self.correct,
            "rejected_candidates": self.rejected_candidates,
            "lost_bytes": self.lost_bytes,
            "first_frame_offset": self.first_frame_offset,
            "bytes_scanned": self.bytes_scanned,
            "recovery": round(self.recovery, 4),
            "loss": round(self.loss, 4),
        }


def measure(capture: Capture, result: DecodeResult) -> Outcome:
    expected = capture.expected
    expected_set = set(expected)
    frames = result.frames
    lost = frames[0].start if frames else result.bytes_scanned
    for previous, current in zip(frames, frames[1:], strict=False):
        lost += current.start - previous.end
    return Outcome(
        scenario=capture.name,
        expected=len(expected),
        recovered=len(frames),
        correct=sum(1 for payload in result.payloads if payload in expected_set),
        rejected_candidates=result.rejected,
        lost_bytes=lost,
        first_frame_offset=frames[0].start if frames else result.bytes_scanned,
        bytes_scanned=result.bytes_scanned,
    )


def run(capture: Capture, window: int | None = None) -> Outcome:
    result = decode(capture.stream) if window is None else decode_windows(capture.stream, window)
    return measure(capture, result)


def window_study(
    capture: Capture, windows: tuple[int, ...] = (8, 16, 32, 64, 128, 256)
) -> dict:
    """How many frames survive when the receiver only keeps a small ring buffer."""
    baseline = run(capture)
    rows = []
    for window in windows:
        outcome = run(capture, window)
        rows.append(
            {
                "window": window,
                "recovered": outcome.recovered,
                "lost_bytes": outcome.lost_bytes,
                "matches_full": outcome.recovered == baseline.recovered,
            }
        )
    return {"scenario": capture.name, "baseline": baseline.as_dict(), "windows": rows}
