"""A straight-through fiber output with a perpendicular power-monitor branch."""
# README:BEGIN
from beampath.components import *
# README:END
from beampath.examples import run_example


def build():
    # README:BEGIN
    split = fiber_laser("Input laser") >> fiber_splitter("90:10 splitter", turn="left")
    split.straight() >> fiber_launch("Main output")
    split.turn() >> fiber_power_meter("Power monitor")
    # README:END
    return split


if __name__ == "__main__":
    run_example(build, "fiber_splitter")
