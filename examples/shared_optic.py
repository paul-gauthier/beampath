"""The MZI connected through named inputs on a shared physical optic."""
from beampath import HWP, LP, QWP, beamsplitter, fiber_launch, iris, mirror
from beampath.examples import run_example


def build():
    """Connect the secondary input first, then the primary input."""
    split = fiber_launch() >> beamsplitter("BS1", angle=-45)
    a = split.straight() >> HWP() >> mirror(heading="south")
    b = split.reflect() >> LP() >> QWP() >> mirror(heading="east")
    bs2 = split.setup.add(beamsplitter("BS2", angle=+45))
    b.connect(bs2.input("secondary"))
    a.connect(bs2.input("primary"))
    bs2.reflect() >> fiber_launch(role="couple")
    bs2.straight() >> iris()
    return split


if __name__ == "__main__":
    run_example(build, "shared_optic")
