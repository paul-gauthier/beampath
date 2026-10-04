"""A Franson interferometer with SPDC and two matched unequal-arm analyzers.

The SPDC angle is exaggerated for readability; distances are schematic."""

from beampath.components import beam_block, beamsplitter, detector, fiber_launch, mirror, spdc

setup = fiber_launch("CW pump") >> spdc(opening_angle=60)
setup.out("pump") >> beam_block("Pump dump")

# Mirror the analyzers about the pump axis. The SPDC angle is exaggerated
# for clarity. Each straight short arm has length 600; its long arm adds
# two 300-unit legs, giving the same nonzero imbalance in both analyzers.
for channel, suffix, outward, inward, return_heading in (
    ("signal", "s", "left", "right", "south"),
    ("idler", "i", "right", "left", "north"),
):
    incoming = setup.out(channel).append(mirror("", heading="east"), distance=700)
    split = incoming >> beamsplitter(f"{channel.capitalize()}\n50:50", turn=outward)
    short = split.straight()
    long = split.reflect().append(mirror(f"Long {suffix}\nPZT phase φ{suffix}", heading="east"),
                                  distance=300)
    long.append(mirror("", heading=return_heading), distance=600)
    combined = short.join(long, beamsplitter("50:50", turn=inward))
    combined.straight() >> detector(f"D{suffix}+")
    combined.reflect() >> detector(f"D{suffix}−")
