"""A laser-driven polarization chain with a folded path and fiber output."""

from beampath.components import *

setup = (
    laser()
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
