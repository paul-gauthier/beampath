"""Pin a fiber monitor above a beam section and let the cable router connect it."""
# DOCS:BEGIN
from beampath.components import *
# DOCS:END
from beampath.examples import run_example


def build():
    # DOCS:BEGIN
    setup = (
        fiber_laser("Tunable laser")
        >> inline_power_meter("Input power")
        >> fiber_launch()
        >> HWP()
        >> fiber_coupler()
    )
    setup.append(inline_power_meter("Output power"), at=(1900, -400))
    # DOCS:END
    return setup


if __name__ == "__main__":
    run_example(build, "fiber_bends")
