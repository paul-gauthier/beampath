"""A linear chain of polarization optics with folded fiber connections."""

from beampath.components import *

setup = (
    fiber_launch()
    >> mirror(turn="right")
    >> mirror(turn="left")
    >> iris()
    >> LP()
    >> HWP()
    >> QWP()
    >> HWP()
    >> LP()
    >> iris()
    >> mirror(turn="left")
    >> mirror(turn="right")
    >> fiber_coupler()
)
