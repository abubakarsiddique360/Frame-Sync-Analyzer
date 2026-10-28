import json

import pytest

from frame_sync_analyzer.analysis import measure, run, window_study
from frame_sync_analyzer.captures import (
    SCENARIOS,
    clean,
    dropped_bytes,
    garbage_prefix,
    stuck_flag,
)
from frame_sync_analyzer.cli import main
from frame_sync_analyzer.framing import decode
from frame_sync_analyzer.report import (
    render_frame_table,
    render_hex,
    render_json,
    render_outcome,
    render_table,
    render_windows,
)

PAYLOADS = [b"TEMP=21.5", b"HUM=48", b"TEMP=21.6", b"DOOR=closed", b"BATT=87"]


def test_clean_capture_loses_nothing():
    outcome = run(clean(PAYLOADS))
    assert outcome.recovered == outcome.expected == len(PAYLOADS)
    assert outcome.lost_bytes == 0
    assert outcome.recovery == 1.0


def test_dropped_bytes_cost_a_frame_and_some_sync():
    outcome = run(dropped_bytes(PAYLOADS, drop=3, at=20))
    assert outcome.recovered < outcome.expected
    assert outcome.lost_bytes > 3


def test_spurious_flags_are_counted_as_rejections():
    outcome = run(stuck_flag(PAYLOADS, count=5))
    assert outcome.rejected_candidates >= 5


def test_garbage_prefix_is_pure_offset_not_loss():
    outcome = run(garbage_prefix(PAYLOADS, length=17))
    assert outcome.recovered == len(PAYLOADS)
    assert outcome.first_frame_offset == 17
    assert outcome.lost_bytes == 17


def test_measure_matches_decode():
    capture = clean(PAYLOADS)
    result = decode(capture.stream)
    outcome = measure(capture, result)
    assert outcome.recovered == len(result.frames)
    assert outcome.correct == len(PAYLOADS)


def test_window_study_reports_each_window():
    study = window_study(clean(PAYLOADS), windows=(4, 32))
    assert [row["window"] for row in study["windows"]] == [4, 32]
    assert study["windows"][0]["recovered"] == 0
    assert study["windows"][1]["matches_full"] is True


def test_every_scenario_produces_a_capture():
    for factory in SCENARIOS.values():
        capture = factory(PAYLOADS)
        assert capture.stream
        assert capture.expected == tuple(PAYLOADS)
        outcome = run(capture)
        assert outcome.recovered <= outcome.expected


def test_report_table_totals():
    outcomes = [run(clean(PAYLOADS)), run(stuck_flag(PAYLOADS, count=2))]
    text = render_table(outcomes)
    assert "frames recovered" in text
    assert f"{len(PAYLOADS)}/{len(PAYLOADS)}" in text


def test_outcome_report_fields():
    text = render_outcome(run(clean(PAYLOADS)))
    assert "frames recovered" in text
    assert "bytes lost to sync" in text


def test_hex_roundtrip_format():
    text = render_hex(bytes(range(20)))
    assert text.splitlines()[0].startswith("00 01 02")
    assert len(text.splitlines()) == 2


def test_frame_table_lists_payloads():
    text = render_frame_table(PAYLOADS)
    assert "TEMP=21.5" in text


def test_json_report_is_machine_readable():
    payload = json.loads(render_json([run(clean(PAYLOADS)).as_dict()]))
    assert payload[0]["recovered"] == len(PAYLOADS)


def test_windows_report_mentions_baseline():
    assert "full decode recovers" in render_windows(window_study(clean(PAYLOADS), windows=(8, 32)))


@pytest.fixture
def hex_file(tmp_path):
    capture = clean(PAYLOADS)
    path = tmp_path / "capture.hex"
    path.write_text(render_hex(capture.stream), encoding="utf-8")
    return path, capture


def test_cli_decode(hex_file, capsys):
    path, capture = hex_file
    assert main(["decode", "--file", str(path)]) == 0
    output = capsys.readouterr().out
    assert f"decoded {len(capture.expected)} frame(s)" in output
    assert "TEMP=21.5" in output


def test_cli_decode_missing_file(tmp_path, capsys):
    assert main(["decode", "--file", str(tmp_path / "nope.hex")]) == 2
    assert "error:" in capsys.readouterr().err


def test_cli_decode_bad_hex(tmp_path, capsys):
    path = tmp_path / "bad.hex"
    path.write_text("zz yy", encoding="utf-8")
    assert main(["decode", "--file", str(path)]) == 2
    assert "not hex" in capsys.readouterr().err


def test_cli_crc(capsys):
    assert main(["crc", "--text", "123456789"]) == 0
    assert "0x29B1" in capsys.readouterr().out


def test_cli_encode(capsys):
    assert main(["encode", "--text", "AB"]) == 0
    assert "7E 02 41 42" in capsys.readouterr().out


def test_cli_bench(capsys):
    assert main(["bench"]) == 0
    output = capsys.readouterr().out
    assert "Frame recovery by capture" in output
    assert "captures" in output


def test_cli_bench_json(capsys):
    assert main(["bench", "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(payload) == len(SCENARIOS)


def test_cli_windows(capsys):
    assert main(["windows", "--scenario", "clean"]) == 0
    assert "Ring-buffer size vs recovery" in capsys.readouterr().out


def test_cli_captures(capsys):
    assert main(["captures"]) == 0
    output = capsys.readouterr().out
    assert "line noise" in output
    assert "garbage prefix" in output
