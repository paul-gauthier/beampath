"""A Mach–Zehnder interferometer with a shared recombining beamsplitter."""

from beampath.components import *

setup = laser() >> beamsplitter("NPBS1", turn="left")
lower = setup.straight() >> HWP() >> mirror(heading="north")
upper = setup.reflect() >> mirror(heading="east") >> HWP()
combined = lower.join(upper, beamsplitter("NPBS2", turn="right"))
combined.reflect() >> detector()
combined.straight() >> detector()
