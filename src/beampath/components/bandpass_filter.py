"""The bandpass_filter component and its minimal demonstration."""
from __future__ import annotations
from ..definitions import ComponentDefinition, component, register_component
from ._shared import _art, _straight


register_component(ComponentDefinition(
    "bandpass_filter", "Bandpass filter",
    _art("fs-bandpass-filter.svg", "free-space-optics/flat_2d/svg/18_interference_filters",
         (53, 35), (47, 9, 59, 61), 1.5), _straight))


def bandpass_filter(label: str | None = None):
    """A straight-through free-space bandpass filter."""
    return component("bandpass_filter", label)


def demo():
    """Show bandpass_filter with its open beam or fiber ports."""
    from beampath import beam
    from beampath.components import bandpass_filter

    setup = beam() >> bandpass_filter()
    return setup
