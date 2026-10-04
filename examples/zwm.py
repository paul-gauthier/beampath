"""A Zou–Wang–Mandel induced-coherence setup with two SPDC crystals.

A shared pump feeds both crystals. NL1's idler passes through NL2 along its
idler mode, while the two signals meet at a separate beamsplitter. The 60°
opening angle is exaggerated for schematic readability. The drawing expresses
geometrical overlap; coherence and spectral/polarization matching are assumed.
"""
# DOCS:BEGIN
from beampath import beam
from beampath.components import beamsplitter, fiber_coupler, mirror, spdc
# DOCS:END
from beampath.examples import run_example


def build():
    """Split the pump, overlap the idlers through NL2, and recombine signals."""
    # DOCS:BEGIN
    pump = beam() >> beamsplitter("Pump splitter", turn="right")
    c1 = (pump.straight() >> spdc("NL1", opening_angle=60)).end
    c2 = (
        pump.reflect()
        >> mirror("Pump mirror", heading="east")
        >> spdc("NL2", opening_angle=60)
    ).end

    # The incoming idler continues along NL2's outgoing idler mode.
    c1.out("idler").connect(c2.input("idler_in"))

    s1 = c1.out("signal") >> mirror("Signal 1", heading="east")
    s2 = c2.out("signal") >> mirror("Signal 2", heading="north")
    combined = s1.join(s2, beamsplitter("Signal combiner", turn="left"))
    combined.straight() >> fiber_coupler("Signal detection")
    # DOCS:END
    return pump


if __name__ == "__main__":
    run_example(build, "zwm")
