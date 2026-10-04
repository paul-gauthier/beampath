"""A heralded Hanbury Brown–Twiss measurement of an SPDC single-photon source.

An idler click heralds its signal partner, which is split between D1 and D2.
Conditioning on the herald measures the signal's autocorrelation: in the
low-click-probability regime, `g_h^(2)(0) ≈ N_h N_h12 / (N_h1 N_h2)`, using herald
singles, herald–D1/D2 coincidences, and triple coincidences in consistent windows.
An ideal heralded single photon gives zero triple coincidences; multipair
emission and background can increase them. Coincidence processing is not drawn.

This SPDC version uses the heralded anticorrelation principle of
[Grangier, Roger, and Aspect (1986)](https://doi.org/10.1209/0295-5075/1/4/004).
"""

from beampath.components import bandpass_filter, beam_block, beamsplitter, detector, laser, mirror, spdc

setup = laser("Pump") >> spdc(opening_angle=60)
setup.out("pump") >> beam_block("Pump dump")
setup.out("idler") >> detector("Herald")

signal = setup.out("signal") >> bandpass_filter() >> mirror("", heading="east")
split = signal >> beamsplitter("50:50", turn="left")
split.straight() >> detector("D1")
split.reflect() >> detector("D2")
