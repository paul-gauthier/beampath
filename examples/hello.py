"""A fiber path folded by two mirrors, with a half-wave plate."""
from beampath import HWP, fiber_launch, mirror
from beampath.examples import run_example


def build():
    """Launch a beam, fold it through a waveplate, and couple it into fiber."""
    setup = (
        fiber_launch()
        >> mirror(angle=-45)
        >> HWP()
        >> mirror(angle=+45)
        >> fiber_launch(role="couple")
    )
    return setup


if __name__ == "__main__":
    run_example(build, "hello")
