"""The MZI connected through named inputs on a shared physical optic."""
# README:BEGIN
from beampath.components import *
# README:END
from beampath.examples import run_example


def build():
    """Connect the secondary input first, then the primary input."""
    # README:BEGIN
    split = fiber_launch() >> beamsplitter("NPBS1", angle=-45)
    a = split.straight() >> HWP() >> mirror(heading="south")
    b = split.reflect() >> LP() >> QWP() >> mirror(heading="east")
    npbs2 = split.setup.add(beamsplitter("NPBS2", angle=+45))
    b.connect(npbs2.input("secondary"))
    a.connect(npbs2.input("primary"))
    npbs2.reflect() >> fiber_coupler()
    npbs2.straight() >> iris()
    # README:END
    return split


if __name__ == "__main__":
    run_example(build, "shared_optic")
