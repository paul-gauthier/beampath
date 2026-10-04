"""Reuse a component chain and constrain its final gaps and position."""

from beampath import beam, chain

from beampath.components import *

polarization = chain(LP(), HWP(), QWP())
setup = beam() >> polarization >> polarization  # Six independent optics.
setup.append(iris(), distance=250)
setup.append(mirror(turn="right"), at=(2000, 0))
