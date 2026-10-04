"""A CW-pumped Franson interferometer with matched unequal-arm analyzers.

Signal and idler each pass through an unbalanced Mach–Zehnder interferometer.
The two long arms have the same extra length, controlled by their PZT mirrors.
Select the central coincidence peak (short–short and long–long events) from
the detector time tags; short–long and long–short events fall in side peaks.
The imbalance must exceed the single-photon coherence length while remaining
below the pump coherence length. Drawing distances are schematic units.
"""
from beampath import Artwork, ComponentDefinition, ComponentSpec, Geometry, Port
from beampath.components import beamsplitter, fiber_launch, mirror, spdc
from beampath.examples import run_example


# Keep the two terminal symbols local to this example; neither has an output.
DETECTOR = ComponentDefinition(
    "franson_detector", "Single-photon detector",
    Artwork(
        center=(0, 0), bounds=(-24, -30, 38, 30),
        svg='<svg xmlns="http://www.w3.org/2000/svg">'
            '<path d="M -22,-28 H 8 A 28,28 0 0 1 8,28 H -22 Z" '
            'fill="#dbeafe" stroke="#1e3a5f" stroke-width="3"/>'
            '</svg>',
        attribution="Original beampath Franson example single-photon detector symbol.",
    ),
    resolve=lambda parameters: Geometry((Port("in", "input", position=(-22, 0)),)),
)
BEAM_DUMP = ComponentDefinition(
    "franson_beam_dump", "Pump dump",
    Artwork(
        center=(0, 0), bounds=(-12, -30, 12, 30),
        svg='<svg xmlns="http://www.w3.org/2000/svg">'
            '<rect x="-10" y="-28" width="20" height="56" fill="#333333"/>'
            '</svg>',
        attribution="Original beampath Franson example beam dump symbol.",
    ),
    resolve=lambda parameters: Geometry((Port("in", "input", position=(-10, 0)),)),
)


def build():
    """Draw two matched unbalanced MZIs and four single-photon detectors."""
    source = fiber_launch("CW pump") >> spdc(opening_angle=60)
    source.out("pump") >> ComponentSpec(BEAM_DUMP)

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
        combined.straight() >> ComponentSpec(DETECTOR, f"D{suffix}+")
        combined.reflect() >> ComponentSpec(DETECTOR, f"D{suffix}−")
    return source


if __name__ == "__main__":
    run_example(build, "franson")
