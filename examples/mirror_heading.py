"""Set an absolute mirror heading, then make a relative 90-degree turn."""

from beampath import beam
from beampath.components import *

setup = beam("east") >> mirror(heading="north") >> mirror(turn="right") >> iris()
