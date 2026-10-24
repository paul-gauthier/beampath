"""A Mach–Zehnder interferometer with a shared recombining beamsplitter."""

from beampath import label
from beampath.components import *

setup = laser() >> beamsplitter("NPBS1", turn="left")
lower = setup.straight() >> label("Lower arm") >> HWP() >> mirror(heading="north")
upper = setup.reflect() >> "Upper arm" >> mirror(heading="east") >> HWP()
combined = lower.join(upper, beamsplitter("NPBS2", turn="right"))
combined.reflect() >> detector()
combined.straight() >> detector()
