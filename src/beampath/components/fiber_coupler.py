"""The fiber_coupler component and its minimal demonstration."""
from __future__ import annotations
from ..definitions import ComponentDefinition, component, register_component
from ..geometry import heading
from ._shared import _FIBER_TRANSITION_ARTWORK, _fiber_transition


def _fiber_coupler(parameters):
    return _fiber_transition(parameters, launch=False)


register_component(ComponentDefinition(
    "fiber_coupler", "Fiber coupler", _FIBER_TRANSITION_ARTWORK,
    _fiber_coupler, label_anchor=(85, 27)))


def fiber_coupler(label: str | None = None, *, heading: str | float | None = None):
    """Convert free space to fiber, following the incoming beam heading."""
    parameters = {}
    if heading is not None:
        parameters["heading"] = heading
    return component("fiber_coupler", label, **parameters)


def demo():
    """Show fiber_coupler with its open beam or fiber ports."""
    from beampath import beam
    from beampath.components import fiber_coupler

    setup = beam() >> fiber_coupler()
    return setup
