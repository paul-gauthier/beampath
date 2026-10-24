"""A generic SPDC crystal with pump, signal, and idler branches."""

from beampath.components import *

setup = laser("Pump input") >> "Pump" >> spdc()
setup.out("pump") >> beam_block("Transmitted pump")
setup.out("signal") >> "Signal" >> fiber_coupler()
setup.out("idler") >> "Idler" >> fiber_coupler()
