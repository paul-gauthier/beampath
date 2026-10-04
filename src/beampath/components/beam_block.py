"""The beam_block component and its minimal demonstration."""
from __future__ import annotations
from ..definitions import Artwork, ComponentDefinition, Geometry, Port, component, register_component
from ._shared import _parameters


def _beam_block(parameters):
    _parameters(parameters, ())
    return Geometry((Port("in", "input", position=(-10, 0)),))


register_component(ComponentDefinition(
    "beam_block", "Beam block",
    Artwork((0, 0), (-12, -30, 12, 30),
            package_resource="fs-beam-block.svg",
            attribution="Original beampath schematic artwork for a beam block: "
                        "a dark rectangular absorber."),
    _beam_block))


def beam_block(label: str | None = None):
    """A beam block with one free-space input and no output, following incidence."""
    return component("beam_block", label)


def demo():
    """Show beam_block with its open beam or fiber ports."""
    from beampath import beam
    from beampath.components import beam_block

    setup = beam() >> beam_block()
    return setup
