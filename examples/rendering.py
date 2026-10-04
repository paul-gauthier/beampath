"""Render a polarization chain with custom spacing, labels, and beam color."""

from beampath import Style, beam
from beampath.components import *

style = Style(pitch=220, font_size=20, beam_color="#1f77b4")

setup = beam() >> LP() >> HWP() >> QWP()
