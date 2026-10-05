"""A polarization quantum eraser inspired by the free-space setup of Ma et al. (2013).

The compact SPDC source represents |Ψ+⟩ = (|HV⟩ + |VH⟩) / √2, with source
preparation and collection optics omitted. Assume polarization-preserving routing
and PBSs that transmit H and reflect V in their local bases. PBS1 maps the system
photon's polarization onto paths b (H) and a (V); the 45° HWP makes both arms H
before they meet at the 50:50 NPBS. The environment photon retains the path tag.

The environment HWP selects H/V analysis at 0° or +/− analysis at 22.5°, where
|±⟩ = (|H⟩ ± |V⟩) / √2. These are alternative settings. Scan φ and sort S1/S2
counts by coincidences with E: H/V reveals the path; +/− selects complementary
fringes. Summing over E leaves the system counts independent of φ in either basis.

This idealized diagram uses a manual HWP in place of the experiment's switched
analyzer; the long link, QRNG, and spacetime arrangement are omitted.
See [Ma et al. (2013), Fig. 5](https://doi.org/10.1073/pnas.1213201110).
"""

from beampath.components import HWP, PBS, beam_block, beamsplitter, detector, laser, mirror, spdc

setup = laser("Pump") >> spdc("SPDC\nΨ+", opening_angle=60)
setup.out("pump") >> beam_block("Pump dump")

system = setup.out("signal") >> mirror("System", heading="east") >> PBS("PBS1", turn="left")
b = system.straight() >> mirror("b · H\nPZT phase φ", heading="north")
a = system.reflect() >> mirror("a · V", heading="east") >> HWP("HWP 45°\nV to H")
combined = b.join(a, beamsplitter("NPBS\n50:50", turn="right"))
combined.straight() >> detector("S1")
combined.reflect() >> detector("S2")

environment = (
    setup.out("idler")
    >> mirror("Environment", heading="east")
    >> HWP("Basis HWP\n0° / 22.5°")
    >> PBS("PBS2", turn="right")
)
environment.straight() >> detector("E H / +")
environment.reflect() >> detector("E V / −")
