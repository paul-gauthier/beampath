"""Hong–Ou–Mandel interference: two SPDC photons meet at one 50:50 beamsplitter.

Assume degenerate signal and idler photons with the same polarization, matched
spectral filters, and overlapping spatial modes at the beamsplitter. Scanning
the delay τ produces a dip in D1–D2 coincidences when the wavepackets overlap;
ideal indistinguishable photons leave together through either output.
The labeled delay represents a scanned path length, not a simulated time.

Based on [Hong, Ou, and Mandel (1987)](https://doi.org/10.1103/PhysRevLett.59.2044).
"""

from beampath.components import bandpass_filter, beam_block, beamsplitter, detector, laser, mirror, spdc

setup = laser("Pump") >> spdc("SPDC\nDegenerate", opening_angle=60)
setup.out("pump") >> beam_block("Pump dump")

signal = setup.out("signal") >> bandpass_filter("Matched filter") >> mirror("", heading="east")
idler = setup.out("idler") >> bandpass_filter("Matched filter") >> mirror("Delay τ", heading="north")
combined = signal.join(idler, beamsplitter("50:50", turn="left"))
combined.straight() >> detector("D1")
combined.reflect() >> detector("D2")
