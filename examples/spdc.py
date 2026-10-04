"""A generic SPDC crystal with pump, signal, and idler branches."""

from beampath.components import *

setup = laser("Pump input") >> spdc()
# Small opening angles need longer paths to separate downstream optics.
setup.out("pump").append(iris("Transmitted pump"), distance=800)
setup.out("signal").append(fiber_coupler("Signal"), distance=500)
setup.out("idler").append(fiber_coupler("Idler"), distance=500)
