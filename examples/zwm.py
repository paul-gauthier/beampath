"""A Zou–Wang–Mandel setup with two SPDC crystals and overlapping idler paths.

The shared pump feeds both crystals; their signals meet at a beamsplitter."""

from beampath import beam
from beampath.components import beamsplitter, fiber_coupler, mirror, spdc

setup = beam() >> beamsplitter("Pump splitter", turn="right")
c1 = (setup.straight() >> spdc("NL1", opening_angle=60)).end
c2 = (
    setup.reflect()
    >> mirror("Pump mirror", heading="east")
    >> spdc("NL2", opening_angle=60)
).end

# The incoming idler continues along NL2's outgoing idler mode.
c1.out("idler").connect(c2.input("idler_in"))

s1 = c1.out("signal") >> mirror("Signal 1", heading="east")
s2 = c2.out("signal") >> mirror("Signal 2", heading="north")
combined = s1.join(s2, beamsplitter("Signal combiner", turn="left"))
combined.straight() >> fiber_coupler("Signal detection")
