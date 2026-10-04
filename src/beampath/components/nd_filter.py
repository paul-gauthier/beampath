"""The nd_filter component and its minimal demonstration."""
from __future__ import annotations
from ..definitions import ComponentDefinition, component, register_component
from ._shared import _art, _straight


register_component(ComponentDefinition(
    "nd_filter", "ND filter",
    _art("fs-nd-filter.svg", "free-space-optics/flat_2d/svg/18_nd_filters",
         (53, 35), (47, 9, 59, 61), 1.5), _straight))


def nd_filter(label: str | None = None):
    """A straight-through free-space neutral-density filter."""
    return component("nd_filter", label)


def demo():
    """Show nd_filter with its open beam or fiber ports."""
    from beampath import beam
    from beampath.components import nd_filter

    setup = beam() >> nd_filter()
    return setup
