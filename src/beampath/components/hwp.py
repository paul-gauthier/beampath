"""The HWP component and its minimal demonstration."""
from __future__ import annotations
from ..definitions import ComponentDefinition, component, register_component
from ._shared import _art, _straight


register_component(ComponentDefinition(
    "HWP", "HWP", _art("fs-hwp.svg", "free-space-optics/flat_2d/svg/17_waveplates",
                       (54, 35), (49, 9, 59, 61), 1.5), _straight))


def HWP(label: str | None = None):
    """A straight-through half-wave plate, labeled HWP by default."""
    return component("HWP", label)


def demo():
    """Show HWP with its open beam or fiber ports."""
    from beampath import beam
    from beampath.components import HWP

    setup = beam() >> HWP()
    return setup
