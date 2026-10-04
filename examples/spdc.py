"""A generic SPDC crystal with pump, signal, and idler branches."""
# DOCS:BEGIN
from beampath.components import *
# DOCS:END
from beampath.examples import run_example


def build():
    # DOCS:BEGIN
    source = fiber_launch("Pump input") >> spdc()
    # Small opening angles need longer paths to separate downstream optics.
    source.out("pump").append(iris("Transmitted pump"), distance=800)
    source.out("signal").append(fiber_coupler("Signal"), distance=500)
    source.out("idler").append(fiber_coupler("Idler"), distance=500)
    # DOCS:END
    return source


if __name__ == "__main__":
    run_example(build, "spdc")
