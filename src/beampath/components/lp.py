"""The LP component and its minimal demonstration."""
from __future__ import annotations
from ..definitions import ComponentDefinition, component, register_component
from ._shared import _art, _straight


register_component(ComponentDefinition(
    "LP", "LP",
    _art("fs-wire-grid-polarizer.svg", "free-space-optics/flat_2d/svg/17_polarizers",
         (49, 35), (44, 7, 54, 63), 1.5), _straight))


def LP(label: str | None = None):
    """A straight-through linear polarizer, labeled LP by default."""
    return component("LP", label)


def demo():
    """Show LP with its open beam or fiber ports."""
    from beampath import beam
    from beampath.components import LP

    setup = beam() >> LP()
    return setup
