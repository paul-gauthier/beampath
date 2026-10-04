"""The MZI connected through named inputs on a shared physical optic."""

from beampath.components import *

setup = fiber_launch() >> beamsplitter("NPBS1", turn="right")
a = setup.straight() >> HWP() >> mirror(heading="south")
b = setup.reflect() >> LP() >> QWP() >> mirror(heading="east")
npbs2 = setup.setup.add(beamsplitter("NPBS2", turn="left"))
b.connect(npbs2.input("secondary"))
a.connect(npbs2.input("primary"))
npbs2.reflect() >> fiber_coupler()
npbs2.straight() >> iris()
