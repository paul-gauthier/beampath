"""A straight-through fiber output with a perpendicular power-monitor branch."""

from beampath.components import *

setup = fiber_laser("Input laser") >> fiber_splitter("90:10 splitter", turn="left")
setup.straight() >> "Main fiber" >> fiber_launch("Main output")
setup.turn() >> "Monitor fiber" >> fiber_power_meter("Power monitor")
