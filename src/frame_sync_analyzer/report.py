"""Text reports for frame recovery."""

from __future__ import annotations

import json

from .analysis import Outcome


def render_outcome(outcome: Outcome) -> str:
    lines = [f"Capture: {outcome.scenario}", "=" * 66]
    lines.append(f"bytes scanned        {outcome.bytes_scanned}")
    lines.append(f"frames expected      {outcome.expected}")
    lines.append(f"frames recovered     {outcome.recovered}  ({outcome.recovery * 100:.0f}%)")
    lines.append(f"payloads matching    {outcome.correct}")
    lines.append(f"rejected candidates  {outcome.rejected_candidates}")
    lines.append(
        f"bytes lost to sync   {outcome.lost_bytes}  ({outcome.loss * 100:.1f}% of the stream)"
    )
    lines.append(f"first frame offset   {outcome.first_frame_offset}")
    return "\n".join(lines)


def render_table(outcomes: list[Outcome]) -> str:
    header = (
        f"{'scenario':<18}{'frames':>10}{'recover':>9}{'correct':>9}"
        f"{'rejected':>10}{'lost':>8}"
    )
    lines = ["Frame recovery by capture", "=" * len(header), header]
    for outcome in outcomes:
        lines.append(
            f"{outcome.scenario[:17]:<18}{f'{outcome.recovered}/{outcome.expected}':>10}"
            f"{outcome.recovery * 100:>8.0f}%{outcome.correct:>9}"
            f"{outcome.rejected_candidates:>10}{outcome.lost_bytes:>8}"
        )
    total_expected = sum(item.expected for item in outcomes)
    total_frames = sum(item.recovered for item in outcomes)
    lines.append("")
    lines.append(
        f"{len(outcomes)} captures   {total_frames}/{total_expected} frames recovered   "
        f"{sum(item.lost_bytes for item in outcomes)} bytes lost"
    )
    return "\n".join(lines)


def render_windows(study: dict) -> str:
    lines = [f"Ring-buffer size vs recovery ({study['scenario']})", "=" * 62]
    lines.append(f"{'window':>8}{'recovered':>12}{'lost bytes':>13}{'full match':>12}")
    for row in study["windows"]:
        lines.append(
            f"{row['window']:>8}{row['recovered']:>12}{row['lost_bytes']:>13}"
            f"{('yes' if row['matches_full'] else 'no'):>12}"
        )
    lines.append("")
    lines.append(
        f"full decode recovers {study['baseline']['recovered']} frames; "
        "a window smaller than one frame cannot see a whole candidate"
    )
    return "\n".join(lines)


def render_json(payload) -> str:
    return json.dumps(payload, indent=2)


def render_hex(stream: bytes) -> str:
    return "\n".join(
        " ".join(f"{byte:02X}" for byte in stream[offset : offset + 16]).strip()
        for offset in range(0, len(stream), 16)
    )


def render_frame_table(payloads: list[bytes]) -> str:
    lines = [f"{'#':>3}{'len':>5}  payload", "-" * 50]
    for index, payload in enumerate(payloads, start=1):
        text = payload.decode("utf-8", errors="replace")
        lines.append(f"{index:>3}{len(payload):>5}  {text}")
    return "\n".join(lines)
