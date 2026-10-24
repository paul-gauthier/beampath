"""Label beam and fiber connections with label(...) or a bare string."""

from beampath import label
from beampath.components import HWP, fiber_coupler, fiber_laser, fiber_launch, fiber_power_meter

setup = (
    fiber_laser("Laser")
    >> label("Input fiber", "2 m")
    >> fiber_launch()
    >> "780 nm"
    >> HWP()
    >> label("Prepared beam")
    >> fiber_coupler()
    >> "Output fiber"
    >> fiber_power_meter("Power")
)
