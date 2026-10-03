"""A straight-through fiber output with a perpendicular power-monitor branch."""
# DOCS:BEGIN
from beampath.components import *
# DOCS:END
from beampath.examples import run_example


def build():
    # DOCS:BEGIN
    split = fiber_laser("Input laser") >> fiber_splitter("90:10 splitter", turn="left")
    split.straight() >> fiber_launch("Main output")
    split.turn() >> fiber_power_meter("Power monitor")
    # DOCS:END
    return split


if __name__ == "__main__":
    run_example(build, "fiber_splitter")
