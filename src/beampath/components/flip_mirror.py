"""The flip-in/out mirror component and its minimal demonstration."""
from __future__ import annotations

from ..definitions import Artwork, ComponentDefinition, Geometry, Port, component, register_component
from ..errors import ComponentError
from ._shared import _parameters


def _flip_mirror(parameters):
    _parameters(parameters, ("turn",))
    turn = parameters.get("turn", "left")
    if not isinstance(turn, str) or turn.lower() not in {"left", "right"}:
        raise ComponentError("Flip mirror turn must be 'left' or 'right'")
    left = turn.lower() == "left"
    # Reflecting x then rotating 180 degrees mirrors the assembly about the beam.
    return Geometry((Port("in", "input"), Port("straight", "output"),
                     Port("reflect", "output", 270 if left else 90)),
                    artwork_rotation=0 if left else 180, reflected=not left)


register_component(ComponentDefinition(
    "flip_mirror", "Flip mirror",
    Artwork((0, 0), (-39, -19, 22, 55), 1.6,
            package_resource="fs-flip-mirror.svg",
            attribution="Original beampath schematic artwork for a flip-in/out mirror: "
                        "a 45-degree reflecting surface and a perpendicular dashed "
                        "flipped-out position sharing a pivot, with the motor clear "
                        "of the beam paths."),
    _flip_mirror))


def flip_mirror(label: str | None = None, *lines: str, turn: str = "left"):
    """A flip-in/out mirror with straight-through and reflected output paths.

    straight() selects the bypass with the mirror out; reflect() selects the
    path with the mirror in, turning 90° left (default) or right according to
    turn. Directions are relative to the incoming beam at the single "in" port.
    The two outputs depict alternative mirror positions. The dashed artwork
    indicates the alternate mirror position.
    """
    return component("flip_mirror", label, *lines, turn=turn)


def demo():
    """Show a flip mirror with its input and two open output paths."""
    from beampath import beam
    from beampath.components import flip_mirror

    setup = beam() >> flip_mirror()
    return setup
