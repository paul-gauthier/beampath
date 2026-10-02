#!/usr/bin/env python3
"""Generate reference diagrams through the beampath DSL."""
import argparse
from pathlib import Path

from beampath.examples import cage_system, mzi

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diagram", choices=("cage", "mzi"), default="cage")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "build/examples")
    parser.add_argument("--png", action="store_true", help="Also export PNG; requires beampath[png] and native Cairo")
    parser.add_argument("--width", type=int, default=7200, help="PNG width in pixels")
    args = parser.parse_args()
    setup = mzi() if args.diagram == "mzi" else cage_system()
    name = "mzi" if args.diagram == "mzi" else "thorlabs_cage_system"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    filename = args.output_dir / (name + ".svg")
    setup.save(filename)
    print(f"Created {filename} ({len(setup.setup.optics)} optics, {len(setup.setup.connections)} connections)")
    if args.png:
        filename = args.output_dir / (name + ".png")
        setup.save(filename, width=args.width, dpi=600)
        print(f"Created {filename}")


if __name__ == "__main__":
    main()
