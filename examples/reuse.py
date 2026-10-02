"""Reuse a component chain and constrain its final gaps and position."""
from beampath import HWP, LP, QWP, beam, chain, iris, mirror
from beampath.examples import run_example


def build():
    """Insert two independent copies of a polarization chain."""
    polarization = chain(LP(), HWP(), QWP())
    path = beam() >> polarization >> polarization  # Six independent optics.
    path.append(iris(), distance=250)
    path.append(mirror(turn="right"), at=(2000, 0))
    return path


if __name__ == "__main__":
    run_example(build, "reuse")
