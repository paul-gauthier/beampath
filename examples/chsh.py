"""A CHSH Bell test with independently chosen Alice and Bob polarization analyzers.

The compact source represents compensated SPDC prepared in the singlet
|Ψ−⟩ = (|HV⟩ − |VH⟩) / √2; source preparation and collection optics are omitted.
Assume polarization-preserving routing and a PBS convention that transmits H
and reflects V in each analyzer's local basis. Each HWP at θ/2 selects the
linear-polarization measurement basis θ, with transmitted/reflected outcomes +/−.

Alice chooses a = 0° or a′ = 45°; Bob chooses b = 22.5° or b′ = −22.5°.
The slash-separated HWP labels are alternative settings, not simultaneous ones.
From coincidence counts, E = (N++ + N−− − N+− − N−+) / Ntotal. The ideal singlet
gives E(a,b) = −cos(2(a−b)) and |S| = 2√2 for
S = E(a,b) + E(a,b′) + E(a′,b) − E(a′,b′).

See [CHSH (1969)](https://doi.org/10.1103/PhysRevLett.23.880) and the entangled
source of [Kwiat et al. (1995)](https://doi.org/10.1103/PhysRevLett.75.4337).
"""

from beampath.components import HWP, PBS, beam_block, detector, laser, mirror, spdc


def analyzer(path, name, angles, *, turn):
    settings = " / ".join(f"{angle / 2:g}°" for angle in angles)
    split = path >> HWP(f"{name} HWP\n{settings}") >> PBS(turn=turn)
    split.straight() >> detector(f"{name} +")
    split.reflect() >> detector(f"{name} −")


alice_angles = (0, 45)
bob_angles = (22.5, -22.5)
setup = laser("Pump") >> spdc("SPDC\nΨ−", opening_angle=60)
setup.out("pump") >> beam_block("Pump dump")
alice = setup.out("signal") >> mirror("", heading="east")
bob = setup.out("idler") >> mirror("", heading="east")
analyzer(alice, "Alice", alice_angles, turn="left")
analyzer(bob, "Bob", bob_angles, turn="right")
