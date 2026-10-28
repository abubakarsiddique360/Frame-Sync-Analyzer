"""Command line entry point for frame-sync."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .analysis import run, window_study
from .captures import SCENARIOS
from .framing import FrameError, crc16_ccitt, decode, encode
from .report import (
    render_frame_table,
    render_hex,
    render_json,
    render_outcome,
    render_table,
    render_windows,
)

SCENARIO_PAYLOADS = [
    b"TEMP=21.5",
    b"HUM=48",
    b"TEMP=21.6",
    b"DOOR=closed",
    b"TEMP=21.5",
    b"BATT=87",
    b"HUM=49",
    b"TEMP=21.7",
    b"DOOR=open",
    b"TEMP=21.8",
]


def _read_stream(source: str) -> bytes:
    if source == "-":
        text = sys.stdin.read()
    else:
        with open(source, encoding="utf-8") as handle:
            text = handle.read()
    cleaned = text.replace(",", " ").replace("0x", " ").replace("0X", " ")
    try:
        return bytes(int(part, 16) for part in cleaned.split())
    except ValueError as exc:
        raise FrameError(f"input is not hex: {exc}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="frame-sync",
        description="Decode a length-prefixed CRC-16 serial stream and measure resync cost.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    bench = sub.add_parser("bench", help="decode every built-in capture and compare")
    bench.add_argument("--format", choices=("text", "json"), default="text")

    dec = sub.add_parser("decode", help="decode a hex dump of a capture")
    dec.add_argument("--file", required=True, help="hex text file, or - for stdin")

    crc = sub.add_parser("crc", help="checksum a text payload")
    crc.add_argument("--text", required=True)

    enc = sub.add_parser("encode", help="wrap a text payload in a frame and print the hex")
    enc.add_argument("--text", required=True)

    win = sub.add_parser("windows", help="recovery against ring-buffer size")
    win.add_argument("--scenario", choices=tuple(SCENARIOS), default="clean")

    sub.add_parser("captures", help="list the built-in captures")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "captures":
        for name, factory in SCENARIOS.items():
            capture = factory(SCENARIO_PAYLOADS)
            damage = f"  ({', '.join(capture.damage)})" if capture.damage else ""
            label = name.ljust(16)
            print(f"{label}{len(capture.stream):>5} bytes  {len(capture.expected)} frames{damage}")
        return 0

    if args.command == "crc":
        payload = args.text.encode("utf-8")
        print(f"payload  {payload!r}")
        print(f"crc16    0x{crc16_ccitt(payload):04X}")
        return 0

    if args.command == "encode":
        try:
            frame = encode(args.text.encode("utf-8"))
        except FrameError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(render_hex(frame))
        return 0

    if args.command == "decode":
        try:
            stream = _read_stream(args.file)
        except (OSError, FrameError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        result = decode(stream)
        print(f"decoded {len(result.frames)} frame(s) from {len(stream)} bytes")
        print()
        print(render_frame_table(list(result.payloads)))
        return 0

    if args.command == "windows":
        study = window_study(SCENARIOS[args.scenario](SCENARIO_PAYLOADS))
        print(render_windows(study))
        return 0

    outcomes = [run(factory(SCENARIO_PAYLOADS)) for factory in SCENARIOS.values()]
    if args.format == "json":
        print(render_json([outcome.as_dict() for outcome in outcomes]))
    else:
        print(render_table(outcomes))
        print()
        for outcome in outcomes:
            if outcome.scenario == "line noise":
                print(render_outcome(outcome))
                break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
