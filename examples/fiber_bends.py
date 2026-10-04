"""Pin a fiber monitor above a beam section and let the cable router connect it."""

from beampath.components import *

setup = (
    fiber_laser("Tunable laser")
    >> inline_power_meter("Input power")
    >> fiber_launch()
    >> HWP()
    >> fiber_coupler()
)
setup.append(inline_power_meter("Output power"), at=(1900, -400))
