"""Shared command-line export options for the example scripts."""
import argparse
from pathlib import Path


def add_export_arguments(parser):
    parser.add_argument("--output-dir", type=Path, default=Path("build/examples"))
    parser.add_argument("--png", action="store_true",
                        help="Also export PNG; requires beampath[png] and native Cairo")
    parser.add_argument("--width", type=int, default=2400, help="PNG width in pixels")


def export_setup(setup, name, args, *, style=None):
    args.output_dir.mkdir(parents=True, exist_ok=True)
    svg = args.output_dir / f"{name}.svg"
    setup.save(svg, style=style)
    print(f"Created {svg}")
    if args.png:
        png = args.output_dir / f"{name}.png"
        setup.save(png, style=style, width=args.width, dpi=600)
        print(f"Created {png}")


def run_example(factory, name, *, style=None):
    parser = argparse.ArgumentParser(description=factory.__doc__)
    add_export_arguments(parser)
    args = parser.parse_args()
    export_setup(factory(), name, args, style=style)
