"""The inline_power_meter component and its minimal demonstration."""
from __future__ import annotations
from ..definitions import ComponentDefinition, Geometry, Port, component, register_component
from ._shared import _art, _parameters


def _fiber_meter(parameters):
    _parameters(parameters, ())
    return Geometry((Port("in", "input", medium="fiber"),
                     Port("out", "output", medium="fiber")))


register_component(ComponentDefinition(
    "inline_power_meter", "Inline power meter",
    _art("f-inline-power-meter.svg", "fiber-optics/flat_2d/svg/11_inline_components",
         (85, 27), (56.5, 25, 113.5, 79), 1.5,
         adaptations="Housing and display match the standalone f-power-meter.svg at the same scale. "
                     "Inline power-meter display changed to 1.23 mW and kept aligned with its housing. "
                     "Embedded through fiber removed; both fiber ports attach at the tap. "
                     "Internal tap fiber matches the routed fiber style."),
    _fiber_meter))


def inline_power_meter(label: str | None = None):
    """A power monitor through which the fiber path continues."""
    return component("inline_power_meter", label)


def demo():
    """Show inline_power_meter with its open beam or fiber ports."""
    from beampath import beam
    from beampath.components import inline_power_meter

    setup = beam() >> inline_power_meter()
    return setup
