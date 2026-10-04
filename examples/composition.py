"""Render a branched stage independently and insert two copies into a setup."""
# DOCS:BEGIN
from beampath import beam
from beampath.components import *


def build_stage():
    split = (
        fiber_launch("Input") >> HWP() >> fiber_coupler("Output")
        >> fiber_splitter("99:1", turn="left")
    )
    split.turn() >> fiber_power_meter("Monitor")
    return split.straight()
# DOCS:END
from beampath.examples import run_example


def build():
    """Connect two independently positioned copies, including their monitors."""
    # DOCS:BEGIN
    stage = build_stage()
    setup = beam() >> fiber_laser("Laser")
    setup.append(stage, at=(300, 0))
    setup.append(stage, at=(300, 600))
    setup >> fiber_power_meter("Final power")
    # DOCS:END
    return setup


if __name__ == "__main__":
    run_example(build, "composition")
