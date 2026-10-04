"""Entanglement swapping with two singlet-pair sources and a partial Bell measurement.

Each compact source represents compensated SPDC preparing
|Ψ−⟩ = (|HV⟩ − |VH⟩) / √2; source preparation and collection optics are omitted.
A shared pulsed pump synchronizes the sources. One photon from each pair meets
at a 50:50 NPBS, with matched spectra, spatial modes, and arrival times; the
other photons go to Alice and Bob's HWP–PBS polarization analyzers.

In the one-pair-per-source sector, a B1–B2 coincidence selects the antisymmetric
singlet of the interfering photons and leaves the remote photons in a singlet.
This identifies one Bell state, not a complete Bell measurement. Fourfold events
(B1, B2, one Alice detector, one Bob detector) verify the swapped correlations;
higher-order SPDC emission and background are neglected. Routing preserves the
local H/V bases, and a HWP at θ/2 selects analyzer angle θ.

Based on [Pan et al. (1998)](https://doi.org/10.1103/PhysRevLett.80.3891).
"""

from beampath.components import HWP, PBS, bandpass_filter, beam_block, beamsplitter, detector, laser, mirror, spdc


def analyzer(path, name, angle, *, turn):
    split = path >> HWP(f"{name} HWP\n{angle}/2") >> PBS(turn=turn)
    split.straight() >> detector(f"{name} +")
    split.reflect() >> detector(f"{name} −")


setup = laser("Pulsed pump") >> beamsplitter("Pump splitter", turn="right")
pair1 = (setup.straight() >> spdc("SPDC 1\nΨ−", opening_angle=60)).end
pair2 = (
    setup.reflect() >> mirror("", heading="east") >> spdc("SPDC 2\nΨ−", opening_angle=60)
).end
for source in (pair1, pair2):
    source.out("pump") >> beam_block("Pump dump")

inner1 = pair1.out("idler") >> bandpass_filter("Matched filter") >> mirror("", heading="east")
inner2 = pair2.out("signal") >> bandpass_filter("Matched filter") >> mirror("Delay τ", heading="north")
bell = inner1.join(inner2, beamsplitter("Bell measurement\n50:50", turn="left"))
bell.straight() >> detector("B1")
bell.reflect() >> detector("B2")

alice = pair1.out("signal") >> mirror("", heading="east")
bob = pair2.out("idler") >> mirror("", heading="east")
analyzer(alice, "Alice", "α", turn="left")
analyzer(bob, "Bob", "β", turn="right")
