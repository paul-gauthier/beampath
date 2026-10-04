"""Draw a collinear SPDC source and its common downstream optical path."""
# DOCS:BEGIN
from beampath.components import *
# DOCS:END
from beampath.examples import run_example


def build():
    # DOCS:BEGIN
    source = fiber_launch("Pump input") >> spdc(opening_angle=0)
    # Select one output to draw the common path through shared optics once.
    source.out("signal") >> HWP() >> fiber_coupler("Collinear output")
    # DOCS:END
    return source


if __name__ == "__main__":
    run_example(build, "spdc_collinear")
