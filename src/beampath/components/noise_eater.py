"""The noise_eater component and its minimal demonstration."""
from __future__ import annotations
from ..definitions import Artwork, ComponentDefinition, component, register_component
from ._shared import _straight


register_component(ComponentDefinition(
    "noise_eater", "Noise eater",
    Artwork((54, 60), (30, 9, 68, 111), 1.5,
            package_resource="fs-noise-eater.svg",
            attribution="Original beampath schematic artwork for a Thorlabs NEL03A noise eater; "
                        "green housing based on the user-supplied Laser Clean-up diagram."),
    _straight))


def noise_eater(label: str | None = None):
    """A straight-through NEL03A noise eater."""
    return component("noise_eater", label)


def demo():
    """Show noise_eater with its open beam or fiber ports."""
    from beampath import beam
    from beampath.components import noise_eater

    setup = beam() >> noise_eater()
    return setup
