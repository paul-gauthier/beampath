"""Four-photon GHZ entanglement by path identity, using four degenerate SPDC sources.

The HH sources emit pairs into (a, b) and (c, d); the VV sources emit pairs
into (a, c) and (b, d). With coherent pumping, indistinguishable modes,
balanced pair amplitudes, and zero relative phase, postselecting one photon
in each output gives (|HHHH⟩ + |VVVV⟩) / √2 in the low-gain regime.
Pump waveplates rotate the polarization between the two source stages.
The drawing shows connectivity; optical delays and phase tuning are omitted.

Based on the path-identity scheme in
[Fig. 1 of the PyTheus paper](https://arxiv.org/pdf/2210.09980#page=6).
"""

from beampath.components import HWP, beam_block, beamsplitter, detector, laser, mirror, spdc

setup = laser("Coherent pump") >> beamsplitter("Pump splitter", turn="right")

hh_ab = (setup.straight() >> spdc("SPDC\nHH", opening_angle=60)).end
hh_cd = (
    setup.reflect() >> mirror("", heading="east") >> spdc("SPDC\nHH", opening_angle=60)
).end
vv_ac = (
    hh_ab.out("pump") >> HWP("Pump HWP\n45°") >> spdc("SPDC\nVV", opening_angle=60)
).end
vv_bd = (
    hh_cd.out("pump") >> HWP("Pump HWP\n45°") >> spdc("SPDC\nVV", opening_angle=60)
).end

# Each first-stage photon continues through a second-stage crystal in the
# same spatial mode as a possible VV photon. Crossings are not junctions.
a = hh_ab.out("signal") >> mirror("", heading=30)
a.connect(vv_ac.input("idler_in"))
hh_ab.out("idler").connect(vv_bd.input("idler_in"))
hh_cd.out("signal").connect(vv_ac.input("signal_in"))
d = hh_cd.out("idler") >> mirror("", heading=-30)
d.connect(vv_bd.input("signal_in"))

for crystal, outputs in ((vv_ac, ("c", "a")), (vv_bd, ("d", "b"))):
    crystal.out("pump") >> beam_block("Pump dump")
    for port, name in zip(("signal", "idler"), outputs):
        crystal.out(port) >> detector(name)
