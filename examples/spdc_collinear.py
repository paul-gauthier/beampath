"""Draw a collinear SPDC source and its common downstream optical path."""

from beampath.components import *

setup = fiber_launch("Pump input") >> spdc(opening_angle=0)
# Select one output to draw the common path through shared optics once.
setup.out("signal") >> HWP() >> fiber_coupler("Collinear output")
