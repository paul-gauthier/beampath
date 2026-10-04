"""The fiber_laser component and its minimal demonstration."""
from __future__ import annotations
from ..definitions import ComponentDefinition, Geometry, Port, component, register_component
from ._shared import _art, _parameters


def _fiber_source(parameters):
    _parameters(parameters, ())
    return Geometry((Port("out", "output", position=(75, 0), medium="fiber"),))


register_component(ComponentDefinition(
    "fiber_laser", "Fiber laser",
    _art("f-laser.svg", "fiber-optics/flat_2d/svg/05_laser_sources",
         (65, 32), (14, 11, 116, 53), 1.5,
         adaptations="Embedded fiber tail removed; fiber connects at the housing."),
    _fiber_source, default_input=None))


def fiber_laser(label: str | None = None):
    """A source with a fiber output and no optical heading."""
    return component("fiber_laser", label)


def demo():
    """Show fiber_laser with its open beam or fiber ports."""
    from beampath import beam
    from beampath.components import fiber_laser

    setup = beam() >> fiber_laser()
    return setup
