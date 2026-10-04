"""A Mach–Zehnder interferometer with a shared recombining beamsplitter."""
# DOCS:BEGIN
from beampath.components import *
# DOCS:END
from beampath.examples._export import run_example


def build():
    """Split two arms and recombine them to create an MZI."""
    # DOCS:BEGIN
    mzi = fiber_launch() >> beamsplitter("NPBS1", turn="left")
    lower = mzi.straight() >> HWP() >> mirror(heading="north")
    upper = mzi.reflect() >> mirror(heading="east") >> HWP()
    combined = lower.join(upper, beamsplitter("NPBS2", turn="right"))
    combined.reflect() >> fiber_coupler()
    combined.straight() >> fiber_coupler()
    # DOCS:END
    return mzi


if __name__ == "__main__":
    run_example(build, "mzi")
