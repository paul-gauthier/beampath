"""The fiber_power_meter component and its minimal demonstration."""
from __future__ import annotations
from ..definitions import ComponentDefinition, Geometry, Port, component, register_component
from ._shared import _art, _parameters


def _fiber_sink(parameters):
    _parameters(parameters, ())
    return Geometry((Port("in", "input", position=(-41.25, 0), medium="fiber"),))


register_component(ComponentDefinition(
    "fiber_power_meter", "Fiber power meter",
    _art("f-power-meter.svg", "fiber-optics/flat_2d/svg/10_test_equipment",
         (57.5, 27), (29, 7, 86, 47), 1.5,
         adaptations="Display readout retained aligned with its housing. "
                     "Embedded fiber line removed; fiber connects at the housing input."),
    _fiber_sink))


def fiber_power_meter(label: str | None = None):
    """A power meter with a single fiber input that ends the path."""
    return component("fiber_power_meter", label)


def demo():
    """Show fiber_power_meter with its open beam or fiber ports."""
    from beampath import beam
    from beampath.components import fiber_power_meter

    setup = beam() >> fiber_power_meter()
    return setup
