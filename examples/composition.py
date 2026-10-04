"""Build a reusable branched stage and connect two copies in stacked rows."""

from beampath import rows
from beampath.components import *


def build_stage():
    split = (
        fiber_launch("Input") >> HWP() >> fiber_coupler("Output")
        >> fiber_splitter("99:1", turn="left")
    )
    split.turn() >> fiber_power_meter("Monitor")
    return split.straight()


stage = build_stage()
cleanup = fiber_laser("Laser") >> stage
setup = rows(cleanup, stage)
setup >> fiber_power_meter("Final power")
