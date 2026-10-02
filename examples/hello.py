"""A fiber path folded by two mirrors, with a half-wave plate."""
# README:BEGIN
from beampath import HWP, fiber_launch, mirror
# README:END
from beampath.examples import run_example


def build():
    """Launch a beam, fold it through a waveplate, and couple it into fiber."""
    # README:BEGIN
    setup = (
        fiber_launch()
        >> mirror(turn="right")
        >> HWP()
        >> mirror(turn="left")
        >> fiber_launch(role="couple")
    )
    # README:END
    return setup


if __name__ == "__main__":
    run_example(build, "hello")
