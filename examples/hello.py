"""A fiber path folded by two mirrors, with a half-wave plate."""
# DOCS:BEGIN
from beampath.components import *
# DOCS:END
from beampath.examples import run_example


def build():
    """Launch a beam, fold it through a waveplate, and couple it into fiber."""
    # DOCS:BEGIN
    setup = (
        fiber_launch()
        >> mirror(turn="right")
        >> HWP()
        >> mirror(turn="left")
        >> fiber_coupler()
    )
    # DOCS:END
    return setup


if __name__ == "__main__":
    run_example(build, "hello")
