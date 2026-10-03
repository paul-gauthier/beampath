"""Render one example or every example as SVG and optionally PNG."""
import argparse
from importlib import import_module

from ._export import add_export_arguments, export_setup

EXAMPLES = (
    "hello", "cage", "mirror_heading", "mzi", "shared_optic", "reuse", "rendering",
    "custom_component", "mixed_fiber", "fiber_bends", "fiber_splitter",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diagram", choices=(*EXAMPLES, "all"), default="cage")
    add_export_arguments(parser)
    args = parser.parse_args()
    names = EXAMPLES if args.diagram == "all" else (args.diagram,)
    for name in names:
        example = import_module(f"beampath.examples.{name}")
        export_setup(example.build(), name, args, style=getattr(example, "STYLE", None))


if __name__ == "__main__":
    main()
