"""The detector component and its minimal demonstration."""
from __future__ import annotations
from ..definitions import Artwork, ComponentDefinition, Geometry, Port, component, register_component
from ._shared import _parameters


def _detector(parameters):
    _parameters(parameters, ())
    return Geometry((Port("in", "input", position=(-22, 0)),))


register_component(ComponentDefinition(
    "detector", "Detector",
    Artwork((0, 0), (-24, -30, 38, 30),
            package_resource="fs-detector.svg",
            attribution="Original beampath schematic artwork for a detector: "
                        "a blue D-shaped housing with a flat beam-entry face."),
    _detector))


def detector(label: str | None = None):
    """A generic detector with one free-space input that ends the beam path.

    The flat face follows the incoming beam. Detector type (such as a
    single-photon detector) belongs in the label.
    """
    return component("detector", label)


def demo():
    """Show detector with its open beam or fiber ports."""
    from beampath import beam
    from beampath.components import detector

    setup = beam() >> detector()
    return setup
