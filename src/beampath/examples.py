"""Examples of a cage-system layout and a Mach–Zehnder interferometer."""
from .components import HWP, LP, QWP, beamsplitter, fiber_launch, iris, mirror


def cage_system():
    return (
        fiber_launch()
        >> mirror(angle=-45)
        >> mirror(angle=45)
        >> iris()
        >> LP()
        >> HWP()
        >> QWP()
        >> HWP()
        >> LP()
        >> iris()
        >> mirror(angle=45)
        >> mirror(angle=-45)
        >> fiber_launch(role="couple")
    )


def mzi():
    split = fiber_launch() >> beamsplitter("BS1", angle=-45)
    a = split.straight() >> HWP() >> mirror(angle=-45)
    b = split.reflect() >> LP() >> QWP() >> mirror(angle=45)
    combined = a.join(b, beamsplitter("BS2", angle=45))
    combined.reflect() >> fiber_launch(role="couple")
    combined.straight() >> iris()
    return split


def main():
    import argparse
    from pathlib import Path

    examples = {"cage": cage_system, "mzi": mzi}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diagram", choices=examples, default="cage")
    parser.add_argument("--output-dir", type=Path, default=Path("build/examples"))
    parser.add_argument("--png", action="store_true",
                        help="Also export PNG; requires beampath[png] and native Cairo")
    parser.add_argument("--width", type=int, default=2400, help="PNG width in pixels")
    args = parser.parse_args()
    setup = examples[args.diagram]()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    svg = args.output_dir / f"{args.diagram}.svg"
    setup.save(svg)
    print(f"Created {svg}")
    if args.png:
        png = args.output_dir / f"{args.diagram}.png"
        setup.save(png, width=args.width, dpi=600)
        print(f"Created {png}")


if __name__ == "__main__":
    main()
