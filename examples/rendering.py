"""Render a polarization chain with custom spacing, labels, and beam color."""
# README:BEGIN
from beampath import Style, beam
from beampath.components import *
# README:END
from beampath.examples import run_example

# README:BEGIN
STYLE = Style(pitch=220, font_size=20, beam_color="#1f77b4")
# README:END


def build():
    """Build a simple chain for inspecting a styled layout and exporting it."""
    # README:BEGIN
    path = beam() >> LP() >> HWP() >> QWP()
    # README:END
    return path


if __name__ == "__main__":
    path = build()
    # README:BEGIN
    layout = path.layout(style=STYLE)
    svg_text = path.to_svg(style=STYLE)
    # README:END
    run_example(lambda: path, "rendering", style=STYLE)
