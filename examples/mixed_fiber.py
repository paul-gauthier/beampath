"""A laser and inline power monitors surrounding a free-space waveplate."""

from beampath import label
from beampath.components import *

setup = (
    fiber_laser("Tunable laser")
    >> label("Input fiber")
    >> inline_power_meter("Input power")
    >> fiber_launch()
    >> "Free-space"
    >> HWP()
    >> fiber_coupler()
    >> "Output fiber"
    >> inline_power_meter("Output power")
)
