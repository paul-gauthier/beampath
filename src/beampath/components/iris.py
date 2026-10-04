"""The iris component and its minimal demonstration."""
from __future__ import annotations
from ..definitions import ComponentDefinition, component, register_component
from ._shared import _art, _straight


register_component(ComponentDefinition(
    "iris", "Iris",
    _art("fs-iris.svg", "free-space-optics/flat_2d/svg/23_apertures_beam_control",
         (50, 40), (24, 14, 76, 66), 1.5), _straight))


def iris(label: str | None = None):
    """A straight-through free-space aperture."""
    return component("iris", label)


def demo():
    """Show iris with its open beam or fiber ports."""
    from beampath import beam
    from beampath.components import iris

    setup = beam() >> iris()
    return setup
