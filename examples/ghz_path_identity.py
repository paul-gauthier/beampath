"""Four-photon GHZ entanglement by path identity, using four degenerate SPDC sources.

Sources I and II emit HH pairs into (a, b) and (c, d); III and IV emit VV
pairs into (a, c) and (b, d). With coherent pumping, indistinguishable modes,
balanced pair amplitudes, and zero relative phase, postselecting one photon
in each output gives (|HHHH⟩ + |VVVV⟩) / √2 in the low-gain regime.
Pump waveplates rotate the polarization between the two source stages.
The drawing shows connectivity; optical delays and phase tuning are omitted.

Based on the path-identity scheme in
[Fig. 1 of the PyTheus paper](https://arxiv.org/pdf/2210.09980#page=6).
"""

from math import sqrt

from beampath import beam
from beampath.components import HWP, beam_block, beamsplitter, detector, fiber_launch, mirror, spdc

# Equal diagonals keep the two source stages symmetric.
span = 1200
height = span / (2 * sqrt(3))
setup = beam(origin=(-700, -height)) >> fiber_launch("Coherent pump")
split = setup >> beamsplitter("Pump splitter", turn="right")

c1 = split.straight().append(spdc("I: HH", opening_angle=60), at=(0, -height)).end
c2 = (split.reflect() >> mirror("", heading="east")).append(
    spdc("II: HH", opening_angle=60), at=(0, height),
).end
c3 = (c1.out("pump") >> HWP("Pump HWP\n45°")).append(
    spdc("III: VV", opening_angle=60), at=(span, -height),
).end
c4 = (c2.out("pump") >> HWP("Pump HWP\n45°")).append(
    spdc("IV: VV", opening_angle=60), at=(span, height),
).end

# Each first-stage photon continues through a second-stage crystal in the
# same spatial mode as a possible VV photon. Crossings are not junctions.
a = c1.out("signal").append(mirror("", heading=30), at=(span / 2, -2 * height))
a.connect(c3.input("idler_in"))
c1.out("idler").connect(c4.input("idler_in"))
c2.out("signal").connect(c3.input("signal_in"))
d = c2.out("idler").append(mirror("", heading=-30), at=(span / 2, 2 * height))
d.connect(c4.input("signal_in"))

for crystal, y, outputs in ((c3, -height, ("c", "a")), (c4, height, ("d", "b"))):
    crystal.out("pump") >> beam_block("Pump dump")
    # Put all four detectors on one output plane, following the ±30° rays.
    for port, turn, name in zip(("signal", "idler"), (-1, 1), outputs):
        crystal.out(port).append(detector(name), at=(span + 400, y + turn * 400 / sqrt(3)))
