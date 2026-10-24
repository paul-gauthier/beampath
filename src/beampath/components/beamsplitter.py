"""The beamsplitter component and its minimal demonstration."""
from __future__ import annotations
from ..definitions import ComponentDefinition, component, register_component
from ._shared import _art, _cube_splitter


register_component(ComponentDefinition(
    "beamsplitter", "NPBS",
    _art("fs-npbs-cube.svg", "free-space-optics/flat_2d/svg/15_nonpolarizing",
         (60, 45), (39, 24, 81, 66), 1.6, source_filename="fs-bs-cube.svg"),
    _cube_splitter, default_input="primary"))


def beamsplitter(label: str | None = None, *lines: str, turn: str = "left"):
    """A non-polarizing cube beamsplitter, labeled NPBS by default.

    turn selects a 90° reflection left (default) or right relative to the
    primary incoming beam. Select outputs with straight() and reflect().
    Inputs are primary (default) and optional secondary.

    Use optic.reverse() to address the same cube from the opposite direction.
    Its default input receives a returning beam from the forward straight arm;
    reflect() exits opposite the forward reflected output, and straight()
    returns toward the source. For eastward primary incidence and turn="left",
    forward reflect() points north and reverse reflect() points south.
    """
    return component("beamsplitter", label, *lines, turn=turn)


def demo():
    """Show beamsplitter with its open beam or fiber ports."""
    from beampath import beam
    from beampath.components import beamsplitter

    setup = beam() >> beamsplitter()
    return setup
