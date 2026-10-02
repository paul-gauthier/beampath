"""A linear chain of polarization optics with folded fiber connections."""
# README:BEGIN
from beampath.components import *
# README:END
from beampath.examples._export import run_example


def build():
    """Connect a cage-system chain between a fiber launch and coupler."""
    # README:BEGIN
    setup = (
        fiber_launch()
        >> mirror(turn="right")
        >> mirror(turn="left")
        >> iris()
        >> LP()
        >> HWP()
        >> QWP()
        >> HWP()
        >> LP()
        >> iris()
        >> mirror(turn="left")
        >> mirror(turn="right")
        >> fiber_launch(role="couple")
    )
    # README:END
    return setup


if __name__ == "__main__":
    run_example(build, "cage")
