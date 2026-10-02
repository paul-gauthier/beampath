"""Render a polarization chain with custom spacing, labels, and beam color."""
from beampath import HWP, LP, QWP, Style, beam
from beampath.examples import run_example

STYLE = Style(pitch=220, font_size=20, beam_color="#1f77b4")


def build():
    """Build a simple chain for inspecting a styled layout and exporting it."""
    path = beam() >> LP() >> HWP() >> QWP()
    return path


if __name__ == "__main__":
    path = build()
    layout = path.layout(style=STYLE)
    svg_text = path.to_svg(style=STYLE)
    run_example(lambda: path, "rendering", style=STYLE)
