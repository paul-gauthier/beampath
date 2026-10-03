"""A Mach–Zehnder interferometer with a shared recombining beamsplitter."""
# DOCS:BEGIN
from beampath.components import *
# DOCS:END
from beampath.examples._export import run_example


def build():
    """Split two arms and recombine them with join()."""
    # DOCS:BEGIN
    split = fiber_launch() >> beamsplitter("NPBS1", angle=-45)
    a = split.straight() >> HWP() >> mirror(heading="south")
    b = split.reflect() >> LP() >> QWP() >> mirror(heading="east")
    combined = a.join(b, beamsplitter("NPBS2", angle=+45))
    combined.reflect() >> fiber_coupler()
    combined.straight() >> iris()
    # DOCS:END
    return split


if __name__ == "__main__":
    run_example(build, "mzi")
