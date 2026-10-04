"""A laser and inline power monitors surrounding a free-space waveplate."""

from beampath.components import *

setup = (
    fiber_laser("Tunable laser")
    >> inline_power_meter("Input power")
    >> fiber_launch()
    >> HWP()
    >> fiber_coupler()
    >> inline_power_meter("Output power")
)
