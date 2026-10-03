"""Render a polarization chain with custom spacing, labels, and beam color."""
# DOCS:BEGIN
from beampath import Style, beam
from beampath.components import *
# DOCS:END
from beampath.examples import run_example

# DOCS:BEGIN
STYLE = Style(pitch=220, font_size=20, beam_color="#1f77b4")
# DOCS:END


def build():
    """Build a simple chain for inspecting a styled layout and exporting it."""
    # DOCS:BEGIN
    path = beam() >> LP() >> HWP() >> QWP()
    # DOCS:END
    return path


if __name__ == "__main__":
    path = build()
    # DOCS:BEGIN
    layout = path.layout(style=STYLE)
    svg_text = path.to_svg(style=STYLE)
    # DOCS:END
    run_example(lambda: path, "rendering", style=STYLE)
