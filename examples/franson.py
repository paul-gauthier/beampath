"""A CW-pumped Franson interferometer with matched unequal-arm analyzers.

Signal and idler each pass through an unbalanced Mach–Zehnder interferometer.
The two long arms have the same extra length, controlled by their PZT mirrors.
Select the central coincidence peak (short–short and long–long events) from
the detector time tags; short–long and long–short events fall in side peaks.
The imbalance must exceed the single-photon coherence length while remaining
below the pump coherence length. Drawing distances are schematic units.
"""
from beampath.components import beam_block, beamsplitter, detector, fiber_launch, mirror, spdc
from beampath.examples import run_example


def build():
    """Draw two matched unbalanced MZIs and four single-photon detectors."""
    source = fiber_launch("CW pump") >> spdc(opening_angle=60)
    source.out("pump") >> beam_block("Pump dump")

    # Mirror the analyzers about the pump axis. The SPDC angle is exaggerated
    # for clarity. Each straight short arm has length 600; its long arm adds
    # two 300-unit legs, giving the same nonzero imbalance in both analyzers.
    for channel, suffix, outward, inward, return_heading in (
        ("signal", "s", "left", "right", "south"),
        ("idler", "i", "right", "left", "north"),
    ):
        incoming = source.out(channel).append(mirror("", heading="east"), distance=700)
        split = incoming >> beamsplitter(f"{channel.capitalize()}\n50:50", turn=outward)
        short = split.straight()
        long = split.reflect().append(mirror(f"Long {suffix}\nPZT phase φ{suffix}", heading="east"),
                                      distance=300)
        long.append(mirror("", heading=return_heading), distance=600)
        combined = short.join(long, beamsplitter("50:50", turn=inward))
        combined.straight() >> detector(f"D{suffix}+")
        combined.reflect() >> detector(f"D{suffix}−")
    return source


if __name__ == "__main__":
    run_example(build, "franson")
