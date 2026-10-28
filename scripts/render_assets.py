"""Regenerate README assets from real runs.

Usage:  python scripts/render_assets.py
Writes: docs/results.json, docs/images/bench.png,
        docs/images/resync-map.png, docs/images/window-vs-recovery.svg
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from frame_sync_analyzer.analysis import run, window_study  # noqa: E402
from frame_sync_analyzer.captures import SCENARIOS, line_noise  # noqa: E402
from frame_sync_analyzer.cli import SCENARIO_PAYLOADS  # noqa: E402
from frame_sync_analyzer.framing import decode  # noqa: E402
from frame_sync_analyzer.report import (  # noqa: E402
    render_outcome,
    render_table,
    render_windows,
)

BG = "#0d1117"
CHROME = "#161b22"
FG = "#e6edf3"
MUTED = "#8b949e"
ACCENT = "#79c0ff"
GOOD = "#2ea043"
BAD = "#cf222e"


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for name in ("consola.ttf", "cour.ttf", "DejaVuSansMono.ttf"):
        candidate = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def render_terminal(text: str, out_path: Path, title: str) -> None:
    font = load_font(15)
    lines = text.expandtabs(4).splitlines() or [""]
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    char_width = probe.textlength("M", font=font)
    line_height = 21
    pad = 24
    width = int(max(len(line) for line in lines) * char_width) + pad * 2
    height = pad * 2 + len(lines) * line_height + 44
    image = Image.new("RGB", (max(width, 760), height), BG)
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, image.width, 34], fill=CHROME)
    for index, color in enumerate(("#ff5f56", "#ffbd2e", "#27c93f")):
        draw.ellipse([16 + index * 22, 10, 28 + index * 22, 22], fill=color)
    draw.text((92, 9), title, font=load_font(13), fill=MUTED)

    for row, line in enumerate(lines):
        color = FG
        stripped = line.strip()
        if line.startswith("$"):
            color = ACCENT
        elif stripped.endswith("%") and "recover" not in stripped:
            color = GOOD
        elif "recover" in stripped or "frames" in stripped or stripped.startswith("scenario"):
            color = MUTED
        draw.text((pad, 50 + row * line_height), line, font=font, fill=color)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path)


def render_resync_map(captures: dict, out_path: Path) -> None:
    names = list(captures)
    figure, axes = plt.subplots(len(names), 1, figsize=(10.4, 1.05 * len(names) + 0.9))
    figure.patch.set_facecolor("#ffffff")
    axes = list(axes)
    for axis, name in zip(axes, names, strict=True):
        capture = captures[name]
        result = decode(capture.stream)
        axis.add_patch(
            Rectangle((0, 0), len(capture.stream), 1, facecolor="#f6f8fa", edgecolor="#d0d7de",
                      linewidth=0.6)
        )
        cursor = 0
        for frame in result.frames:
            if frame.start > cursor:
                axis.add_patch(
                    Rectangle((cursor, 0), frame.start - cursor, 1, facecolor=BAD, alpha=0.28,
                              edgecolor="none")
                )
            axis.add_patch(
                Rectangle((frame.start, 0), frame.size, 1, facecolor=GOOD, alpha=0.85,
                          edgecolor="none")
            )
            cursor = frame.end
        if cursor < len(capture.stream):
            axis.add_patch(
                Rectangle((cursor, 0), len(capture.stream) - cursor, 1, facecolor=BAD,
                          alpha=0.28, edgecolor="none")
            )
        outcome = run(capture)
        axis.set_xlim(0, len(capture.stream))
        axis.set_ylim(0, 1)
        axis.set_yticks([])
        axis.set_ylabel(f"{name}\n{outcome.recovered}/{outcome.expected}", rotation=0,
                        ha="right", va="center", fontsize=8)
        axis.tick_params(axis="x", labelsize=7)
        for spine in ("top", "right", "left"):
            axis.spines[spine].set_visible(False)
    axes[-1].set_xlabel(
        "byte offset in the captured stream  (green = accepted frame, red = bytes thrown away)"
    )
    figure.suptitle("What a desync costs: accepted frames and the gaps between them", fontsize=11,
                    x=0.02, ha="left")
    figure.tight_layout(rect=(0.02, 0, 1, 0.96))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(out_path, format="png", dpi=150)
    plt.close(figure)


def render_window_curve(study: dict, out_path: Path) -> None:
    windows = [row["window"] for row in study["windows"]]
    recovered = [row["recovered"] for row in study["windows"]]
    figure, axis = plt.subplots(figsize=(9.0, 3.4))
    figure.patch.set_facecolor("#ffffff")
    axis.step(windows, recovered, where="post", color="#0969da", linewidth=2)
    axis.scatter(windows, recovered, color="#0969da", zorder=3, s=28)
    axis.axhline(study["baseline"]["recovered"], color="#1a7f37", linestyle="--", linewidth=1.2,
                 label=f"full decode: {study['baseline']['recovered']} frames")
    axis.legend(fontsize=8, frameon=False, loc="lower right")
    axis.set_xscale("log", base=2)
    axis.set_xticks(windows)
    axis.set_xticklabels([str(window) for window in windows])
    axis.set_xlabel("ring-buffer size in bytes (log scale)")
    axis.set_ylabel("frames recovered")
    axis.set_title("A ring buffer shorter than one frame recovers nothing", fontsize=10, loc="left")
    axis.grid(linestyle=":", alpha=0.45)
    for spine in ("top", "right"):
        axis.spines[spine].set_visible(False)
    figure.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(out_path, format=out_path.suffix.lstrip("."))
    plt.close(figure)


def main() -> int:
    images = ROOT / "docs" / "images"
    images.mkdir(parents=True, exist_ok=True)
    os.chdir(ROOT)

    captures = {name: factory(SCENARIO_PAYLOADS) for name, factory in SCENARIOS.items()}
    outcomes = [run(capture) for capture in captures.values()]
    noise = line_noise(SCENARIO_PAYLOADS)
    study = window_study(noise)

    payload = {
        "captures": [outcome.as_dict() for outcome in outcomes],
        "window_study": study,
        "max_frame_bytes": max(len(payload) for payload in SCENARIO_PAYLOADS) + 4,
    }
    (ROOT / "docs" / "results.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    terminal = (
        "$ frame-sync bench\n\n"
        + render_table(outcomes)
        + "\n\n$ frame-sync windows --scenario \"line noise\"\n\n"
        + render_windows(study)
        + "\n\n$ frame-sync bench   # detail for one capture\n\n"
        + render_outcome(outcomes[1])
    )
    title = "frame-sync  -  one damaged cable, five captures"
    render_terminal(terminal, images / "bench.png", title)
    render_resync_map(captures, images / "resync-map.png")
    render_window_curve(study, images / "window-vs-recovery.svg")

    print(
        "recovered "
        + ", ".join(f"{item.scenario}={item.recovered}/{item.expected}" for item in outcomes)
        + f" | window study baseline {study['baseline']['recovered']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
