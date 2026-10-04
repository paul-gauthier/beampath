"""Render one example or every example as SVG and optionally PNG and PDF."""
import argparse
from importlib import import_module

from ._export import add_export_arguments, export_setup
from ._discovery import example_names


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    names = example_names()
    parser.add_argument("--diagram", choices=(*names, "all"), default="cage")
    add_export_arguments(parser)
    args = parser.parse_args()
    names = names if args.diagram == "all" else (args.diagram,)
    for name in names:
        example = import_module(f"beampath.examples.{name}")
        export_setup(example.setup, name, args, style=getattr(example, "style", None))


if __name__ == "__main__":
    main()
