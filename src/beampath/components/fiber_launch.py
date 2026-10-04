"""The fiber_launch component and its minimal demonstration."""
from __future__ import annotations
from ..definitions import ComponentDefinition, component, register_component
from ..geometry import heading
from ._shared import _FIBER_TRANSITION_ARTWORK, _fiber_transition


def _fiber_launch(parameters):
    return _fiber_transition(parameters, launch=True)


register_component(ComponentDefinition(
    "fiber_launch", "Fiber launch", _FIBER_TRANSITION_ARTWORK,
    _fiber_launch, label_anchor=(85, 27)))


def fiber_launch(label: str | None = None, *, heading: str | float | None = None):
    """Convert fiber to free space, defaulting to an eastward beam heading."""
    parameters = {}
    if heading is not None:
        parameters["heading"] = heading
    return component("fiber_launch", label, **parameters)


def demo():
    """Show fiber_launch with its open beam or fiber ports."""
    from beampath import beam
    from beampath.components import fiber_launch

    setup = beam() >> fiber_launch()
    return setup
