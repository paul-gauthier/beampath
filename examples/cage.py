"""A linear chain of polarization optics with folded fiber connections."""
from beampath import HWP, LP, QWP, fiber_launch, iris, mirror
from beampath.examples._export import run_example


def build():
    """Connect a cage-system chain between a fiber launch and coupler."""
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
    return setup


if __name__ == "__main__":
    run_example(build, "cage")
