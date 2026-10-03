"""A laser and inline power monitors surrounding a free-space waveplate."""
# DOCS:BEGIN
from beampath.components import *
# DOCS:END
from beampath.examples import run_example


def build():
    # DOCS:BEGIN
    setup = (
        fiber_laser("Tunable laser")
        >> inline_power_meter("Input power")
        >> fiber_launch()
        >> HWP()
        >> fiber_coupler()
        >> inline_power_meter("Output power")
    )
    # DOCS:END
    return setup


if __name__ == "__main__":
    run_example(build, "mixed_fiber")
