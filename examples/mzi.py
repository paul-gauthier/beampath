"""A Mach–Zehnder interferometer with a shared recombining beamsplitter."""
from beampath import HWP, LP, QWP, beamsplitter, fiber_launch, iris, mirror
from beampath.examples._export import run_example


def build():
    """Split two arms and recombine them with join()."""
    split = fiber_launch() >> beamsplitter("BS1", angle=-45)
    a = split.straight() >> HWP() >> mirror(heading="south")
    b = split.reflect() >> LP() >> QWP() >> mirror(heading="east")
    combined = a.join(b, beamsplitter("BS2", angle=+45))
    combined.reflect() >> fiber_launch(role="couple")
    combined.straight() >> iris()
    return split


if __name__ == "__main__":
    run_example(build, "mzi")
