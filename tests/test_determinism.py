from pathlib import Path

from access_rat.cli import main
from access_rat.demo import build_demo, write_demo

ROOT = Path(__file__).resolve().parent.parent


def test_same_seed_gives_identical_data():
    assert build_demo(42) == build_demo(42)


def test_different_seed_changes_memberships_not_structure():
    a, b = build_demo(1), build_demo(2)
    assert a["memberships.csv"] != b["memberships.csv"]
    assert a["group_permissions.csv"] == b["group_permissions.csv"]
    assert a["users.csv"] == b["users.csv"]


def _read_all(directory: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(directory.iterdir())}


def test_analysis_output_is_byte_identical_across_runs(tmp_path):
    write_demo(tmp_path / "data", seed=7)
    for name in ("one", "two"):
        assert main(["analyse", "--data", str(tmp_path / "data"), "--out", str(tmp_path / name)]) == 0
    assert _read_all(tmp_path / "one") == _read_all(tmp_path / "two")


def test_output_does_not_depend_on_input_row_order(tmp_path):
    data = tmp_path / "data"
    write_demo(data, seed=3)
    shuffled = tmp_path / "shuffled"
    shuffled.mkdir()
    for name in ("users.csv", "memberships.csv", "group_permissions.csv", "sod_rules.csv"):
        lines = (data / name).read_text().splitlines()
        header, body = lines[0], lines[1:]
        (shuffled / name).write_text("\n".join([header, *reversed(body)]) + "\n")
    main(["analyse", "--data", str(data), "--out", str(tmp_path / "a")])
    main(["analyse", "--data", str(shuffled), "--out", str(tmp_path / "b")])
    for name in ("mapping.csv", "impact.csv", "roles.csv"):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()


def test_committed_examples_are_current(tmp_path):
    """The examples folder must be exactly what the tool produces today (seed 42)."""
    examples = ROOT / "examples"
    if not (examples / "demo-data").is_dir():
        return
    write_demo(tmp_path / "data", seed=42)
    main(["analyse", "--data", str(tmp_path / "data"), "--out", str(tmp_path / "out")])
    assert _read_all(tmp_path / "data") == _read_all(examples / "demo-data")
    assert _read_all(tmp_path / "out") == _read_all(examples / "demo-output")
    main(["analyse", "--data", str(tmp_path / "data"), "--out", str(tmp_path / "agg"), "--max-gain-share", "1"])
    assert _read_all(tmp_path / "agg") == _read_all(examples / "demo-output-aggressive")
