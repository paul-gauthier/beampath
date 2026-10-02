"""A Mach–Zehnder interferometer with a shared recombining beamsplitter."""
# README:BEGIN
from beampath.components import *
# README:END
from beampath.examples._export import run_example


def build():
    """Split two arms and recombine them with join()."""
    # README:BEGIN
    split = fiber_launch() >> beamsplitter("BS1", angle=-45)
    a = split.straight() >> HWP() >> mirror(heading="south")
    b = split.reflect() >> LP() >> QWP() >> mirror(heading="east")
    combined = a.join(b, beamsplitter("BS2", angle=+45))
    combined.reflect() >> fiber_launch(role="couple")
    combined.straight() >> iris()
    # README:END
    return split


if __name__ == "__main__":
    run_example(build, "mzi")
