"""A laser beam folded by two mirrors, with a half-wave plate and fiber output."""

from beampath.components import *

setup = (
    laser()
    >> mirror(turn="right")
    >> HWP()
    >> mirror(turn="left")
    >> fiber_coupler()
)
