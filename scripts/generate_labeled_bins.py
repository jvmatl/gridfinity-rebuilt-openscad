#!/usr/bin/env python3
"""Generate labeled Gridfinity bin 3MFs from JSON descriptions."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PACKAGER = SCRIPT_DIR / "make_orca_3mf.py"
DEFAULT_TEMPLATE = SCRIPT_DIR / "orca_multimaterial_template.3mf"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate one Orca-compatible 3MF per Gridfinity bin JSON description.",
        epilog=(
            "JSON may be a list or an object with a 'bins' list. Example bin: "
            "{'filename':'m3x12','label':'M3x12','x':1,'y':1,'z':4,"
            "'stacking_lip':true,'magnet_holes':true}. "
            "Use 'columns' for one-row column subdivisions."
        ),
    )
    parser.add_argument("input", type=Path, help="JSON file containing bin descriptions")
    parser.add_argument("--models-dir", type=Path, default=Path("models"), help="Output directory for 3MF files")
    parser.add_argument("--component", type=Path, default=Path("labeled_gridfinity_bin.scad"), help="Reusable OpenSCAD component")
    parser.add_argument("--packager", type=Path, default=DEFAULT_PACKAGER, help="make_orca_3mf.py path")
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE, help="Optional Orca 3MF template")
    parser.add_argument("--tmp-root", type=Path, default=Path(tempfile.gettempdir()), help="Root directory for transient SCAD/STL files")
    parser.add_argument("--body-color", default="#FFFFFF", help="Filament 1 display color")
    parser.add_argument("--text-color", default="#000000", help="Filament 2 display color")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without running OpenSCAD or packager")
    parser.add_argument("--verbose-commands", action="store_true", help="Print each command before running it")
    return parser.parse_args()


def fail(message: str) -> None:
    raise SystemExit(f"error: {message}")


def load_bins(path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON in {path}: {exc}")
    if isinstance(data, dict):
        data = data.get("bins")
    if not isinstance(data, list):
        fail("input must be a JSON list or an object with a 'bins' list")
    bins: list[dict[str, Any]] = []
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            fail(f"bin #{index + 1} must be an object")
        bins.append(item)
    return bins


def safe_filename(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        fail("each bin needs a non-empty 'filename' or 'base_filename'")
    name = value.strip()
    if Path(name).name != name:
        fail(f"filename must not include directories: {name!r}")
    sanitized = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("._")
    if not sanitized:
        fail(f"filename has no usable characters: {name!r}")
    return sanitized


def bool_value(item: dict[str, Any], key: str, default: bool) -> bool:
    value = item.get(key, default)
    if not isinstance(value, bool):
        fail(f"{key!r} must be true or false")
    return value


def positive_int(item: dict[str, Any], key: str, default: int | None = None) -> int:
    if key not in item:
        if default is None:
            fail(f"missing required integer field {key!r}")
        value = default
    else:
        value = item[key]
    if not isinstance(value, int) or value <= 0:
        fail(f"{key!r} must be a positive integer")
    return value


def label_to_lines(label: Any) -> list[str]:
    if label is None:
        return []
    if isinstance(label, str):
        return [] if label.strip() == "" else label.splitlines()
    if isinstance(label, list) and all(isinstance(line, str) for line in label):
        return [line for line in label if line.strip() != ""]
    fail("'label' must be a string, list of strings, or null")


def label_lines_and_surface(item: dict[str, Any]) -> tuple[list[str], bool]:
    has_label = "label" in item
    lines = label_to_lines(item.get("label"))

    if "label_surface" in item:
        label_surface = bool_value(item, "label_surface", True)
    else:
        label_surface = has_label
    if lines and not label_surface:
        fail("label text requires label_surface=true")
    return lines, label_surface


def columns_and_surface(item: dict[str, Any]) -> tuple[list[float], list[list[str]], bool] | None:
    if "columns" not in item:
        return None
    if "label" in item:
        fail("use either top-level 'label' or 'columns', not both")
    columns = item["columns"]
    if not isinstance(columns, list) or not columns:
        fail("'columns' must be a non-empty list")

    weights: list[float] = []
    labels: list[list[str]] = []
    has_label_key = False
    for index, column in enumerate(columns):
        if isinstance(column, str):
            weight = 1
            label = column
            has_label_key = True
        elif isinstance(column, dict):
            weight = column.get("weight", 1)
            label = column.get("label")
            has_label_key = has_label_key or "label" in column
        else:
            fail(f"column #{index + 1} must be an object or label string")
        if not isinstance(weight, (int, float)) or weight <= 0:
            fail(f"column #{index + 1} weight must be a positive number")
        weights.append(weight)
        labels.append(label_to_lines(label))

    if "label_surface" in item:
        label_surface = bool_value(item, "label_surface", True)
    else:
        label_surface = has_label_key
    if any(labels) and not label_surface:
        fail("column label text requires label_surface=true")
    return weights, labels, label_surface


def scad_string(value: str) -> str:
    return json.dumps(value)


def scad_bool(value: bool) -> str:
    return "true" if value else "false"


def scad_string_array(values: list[str]) -> str:
    return "[" + ",".join(scad_string(value) for value in values) + "]"


def scad_number_array(values: list[float]) -> str:
    return "[" + ",".join(str(value) for value in values) + "]"


def scad_nested_string_array(values: list[list[str]]) -> str:
    return "[" + ",".join(scad_string_array(value) for value in values) + "]"


def wrapper_source(component: Path, cfg: dict[str, Any], part: str) -> str:
    return f"""use <{component.as_posix()}>

labeled_gridfinity_bin(
    label_lines = {scad_string_array(cfg['label_lines'])},
    compartment_label_lines = {scad_nested_string_array(cfg['compartment_label_lines'])},
    column_weights = {scad_number_array(cfg['column_weights'])},
    part = {scad_string(part)},
    grid_size = [{cfg['x']}, {cfg['y']}],
    gridz = {cfg['z']},
    include_lip = {scad_bool(cfg['stacking_lip'])},
    label_surface = {scad_bool(cfg['label_surface'])},
    magnet_holes = {scad_bool(cfg['magnet_holes'])}
);
"""


def log(message: str) -> None:
    print(message, flush=True)


def format_command(command: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in command)


def phase(index: int, total: int, name: str, message: str) -> None:
    log(f"[{index}/{total}] {name}: {message}")


def run(command: list[str], args: argparse.Namespace) -> float | None:
    if args.dry_run or args.verbose_commands:
        log(f"  $ {format_command(command)}")
    if args.dry_run:
        return None
    started = time.monotonic()
    subprocess.run(command, check=True)
    return time.monotonic() - started


def done_message(label: str, elapsed: float | None) -> str:
    if elapsed is None:
        return f"{label} command emitted"
    return f"{label} done in {elapsed:.1f}s"


def normalize_bin(item: dict[str, Any]) -> dict[str, Any]:
    filename = safe_filename(item.get("filename", item.get("base_filename")))
    if "grid_size" in item:
        grid_size = item["grid_size"]
        if not (isinstance(grid_size, list) and len(grid_size) == 2 and all(isinstance(v, int) and v > 0 for v in grid_size)):
            fail("'grid_size' must be a two-item positive integer list")
        x, y = grid_size
    else:
        x = positive_int(item, "x")
        y = positive_int(item, "y")
    z = positive_int(item, "z", item.get("gridz"))

    columns = columns_and_surface(item)
    if columns is None:
        label_lines, label_surface = label_lines_and_surface(item)
        column_weights: list[float] = []
        compartment_label_lines: list[list[str]] = []
    else:
        column_weights, compartment_label_lines, label_surface = columns
        label_lines = []

    return {
        "filename": filename,
        "label_lines": label_lines,
        "compartment_label_lines": compartment_label_lines,
        "column_weights": column_weights,
        "label_surface": label_surface,
        "x": x,
        "y": y,
        "z": z,
        "stacking_lip": bool_value(item, "stacking_lip", True),
        "magnet_holes": bool_value(item, "magnet_holes", True),
    }


def generate_bin(
    cfg: dict[str, Any],
    args: argparse.Namespace,
    tmp_dir: Path,
    component: Path,
    index: int,
    total: int,
) -> Path:
    base = cfg["filename"]
    body_scad = tmp_dir / f"{base}_body.scad"
    body_stl = tmp_dir / f"{base}_body.stl"
    text_scad = tmp_dir / f"{base}_text.scad"
    text_stl = tmp_dir / f"{base}_text.stl"
    output = args.models_dir / f"{base}.3mf"

    if cfg["column_weights"]:
        labels = [" / ".join(lines) if lines else "no text" for lines in cfg["compartment_label_lines"]]
        label_summary = "columns=" + ",".join(labels)
    else:
        label_summary = " / ".join(cfg["label_lines"]) if cfg["label_lines"] else "no text"
    phase(index, total, base, f"start {cfg['x']}x{cfg['y']}x{cfg['z']}U, label={label_summary!r}")

    body_scad.write_text(wrapper_source(component, cfg, "body"))
    phase(index, total, base, "exporting body STL")
    elapsed = run(["openscad", "-o", str(body_stl), str(body_scad)], args)
    phase(index, total, base, done_message("body STL", elapsed))

    has_text = bool(cfg["label_lines"]) or any(cfg["compartment_label_lines"])
    if has_text:
        text_scad.write_text(wrapper_source(component, cfg, "text"))
        phase(index, total, base, "exporting text STL")
        elapsed = run(["openscad", "-o", str(text_stl), str(text_scad)], args)
        phase(index, total, base, done_message("text STL", elapsed))
    else:
        phase(index, total, base, "no text requested; skipping text STL")

    command = [
        "python3",
        str(args.packager),
        "--output",
        str(output),
        "--assembly-name",
        base,
        "--part",
        f"filament_1_white_body={body_stl}",
        "--extruder",
        "filament_1_white_body=1",
        "--filament-color",
        f"1={args.body_color}",
    ]
    if args.template and args.template.exists():
        command.extend(["--template", str(args.template)])
    if has_text:
        command.extend([
            "--part",
            f"filament_2_black_text={text_stl}",
            "--extruder",
            "filament_2_black_text=2",
            "--filament-color",
            f"2={args.text_color}",
        ])
    phase(index, total, base, "packaging 3MF")
    elapsed = run(command, args)
    if elapsed is None:
        phase(index, total, base, f"3MF package command emitted -> {output}")
    else:
        phase(index, total, base, f"done in {elapsed:.1f}s -> {output}")
    return output


def main() -> int:
    args = parse_args()
    component = args.component.resolve()
    if not component.exists():
        fail(f"component not found: {component}")
    if not args.packager.exists():
        fail(f"packager not found: {args.packager}")
    args.models_dir.mkdir(parents=True, exist_ok=True)
    args.tmp_root.mkdir(parents=True, exist_ok=True)

    raw_bins = load_bins(args.input)
    configs = [normalize_bin(item) for item in raw_bins]
    tmp_dir = Path(tempfile.mkdtemp(prefix="gridfinity_bins_", dir=args.tmp_root))
    log(f"loaded {len(configs)} bin(s)")
    log(f"temporary files: {tmp_dir}")

    outputs = [
        generate_bin(cfg, args, tmp_dir, component, index, len(configs))
        for index, cfg in enumerate(configs, start=1)
    ]
    log("generated:")
    for output in outputs:
        log(f"  {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
