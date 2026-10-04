"""The QWP component and its minimal demonstration."""
from __future__ import annotations
from ..definitions import ComponentDefinition, component, register_component
from ._shared import _art, _straight


register_component(ComponentDefinition(
    "QWP", "QWP", _art("fs-qwp.svg", "free-space-optics/flat_2d/svg/17_waveplates",
                       (54, 35), (49, 9, 59, 61), 1.5), _straight))


def QWP(label: str | None = None):
    """A straight-through quarter-wave plate, labeled QWP by default."""
    return component("QWP", label)


def demo():
    """Show QWP with its open beam or fiber ports."""
    from beampath import beam
    from beampath.components import QWP

    setup = beam() >> QWP()
    return setup
