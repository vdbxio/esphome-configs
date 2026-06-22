#!/usr/bin/env python3
# SPDX-License-Identifier: CC0-1.0
#
# Copy firmware.factory.bin and flash_args from an ESPHome build tree into ./bin/
# with filenames: <device>-<esphome-version>-firmware.factory.bin (and -flash_args).
#
# AI disclaimer: Parts of this file were written or revised with AI assistance;
# verify behavior before relying on it in production.

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path


def find_esphome_data_root(start: Path) -> Path:
    """Directory that contains `.esphome` (usually the repo root you compile from)."""
    for d in (start, *start.parents):
        if (d / ".esphome").is_dir():
            return d
    raise FileNotFoundError(
        "Could not find a `.esphome` directory. Run `esphome compile` from your "
        "config repo first, or invoke this script from that directory tree."
    )


def esphome_version() -> str:
    try:
        out = subprocess.run(
            ["esphome", "version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        return "unknown"
    except subprocess.TimeoutExpired:
        return "unknown"
    if out.returncode != 0 or not out.stdout.strip():
        return "unknown"
    first = out.stdout.strip().splitlines()[0].strip()
    if ":" in first:
        first = first.split(":", 1)[1].strip()
    return re.sub(r"[^\w.\-+]", "_", first) or "unknown"


def build_artifacts_dir(data_root: Path, device: str) -> Path:
    return data_root / ".esphome" / "build" / device / ".pioenvs" / device


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Copy firmware.factory.bin and flash_args from .esphome/build into bin/, "
            "prefixed with <device>-<esphome-version>-. Device name is the stem of "
            "this argument (e.g. flip-c3.yaml → flip-c3)."
        )
    )
    parser.add_argument(
        "name",
        help='Build name or path whose basename stem is used (e.g. flip-c3 or flip-c3.yaml)',
    )
    parser.add_argument(
        "--bin-dir",
        "-o",
        type=Path,
        metavar="DIR",
        help="Output directory (default: <repo-with-.esphome>/bin)",
    )
    args = parser.parse_args()

    device = Path(args.name).stem
    if not device:
        print("error: empty device name after stem", file=sys.stderr)
        return 1

    data_root = find_esphome_data_root(Path.cwd())
    bin_dir = (args.bin_dir.expanduser().resolve() if args.bin_dir else data_root / "bin")
    bin_dir.mkdir(parents=True, exist_ok=True)

    src_dir = build_artifacts_dir(data_root, device)
    ver = esphome_version()
    prefix = f"{device}-{ver}-"

    copied = []
    for name in ("firmware.factory.bin", "flash_args"):
        src = src_dir / name
        if not src.is_file():
            print(f"error: missing build artifact:\n  {src}", file=sys.stderr)
            print(
                "hint: run `esphome compile …` for this device first, "
                "or pass the correct build folder stem as `name`.",
                file=sys.stderr,
            )
            return 1
        dst = bin_dir / f"{prefix}{name}"
        shutil.copy2(src, dst)
        copied.append(dst)

    for p in copied:
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
