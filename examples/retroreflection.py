"""Return a beam through one beamsplitter and send its reflection to a detector."""

from beampath import beam
from beampath.components import beamsplitter, detector, mirror

setup = beam("east") >> beamsplitter("BS", turn="left")
bs = setup.end
back = bs.reverse()

(bs.straight() >> mirror(angle=0)).connect(back.input())
back.reflect() >> detector("xxx")
bs.reflect() >> detector("yyy")
