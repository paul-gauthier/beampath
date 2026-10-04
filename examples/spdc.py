"""A generic SPDC crystal with pump, signal, and idler branches."""

from beampath.components import *

setup = laser("Pump input") >> spdc()
setup.out("pump") >> beam_block("Transmitted pump")
setup.out("signal") >> fiber_coupler("Signal")
setup.out("idler") >> fiber_coupler("Idler")
