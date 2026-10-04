"""The fiber_splitter component and its minimal demonstration."""
from __future__ import annotations
from ..definitions import Artwork, ComponentDefinition, Geometry, Port, component, register_component
from ..errors import ComponentError
from ._shared import _parameters


def _fiber_splitter(parameters):
    _parameters(parameters, ("turn",))
    turn = parameters.get("turn", "left")
    if not isinstance(turn, str) or turn.lower() not in {"left", "right"}:
        raise ComponentError("fiber_splitter turn must be 'left' or 'right'")
    left = turn.lower() == "left"
    # Reflecting x followed by a 180-degree artwork rotation reflects y,
    # so the right-turn curve keeps the through path running left to right.
    return Geometry((
        Port("in", "input", position=(-75, 0), medium="fiber"),
        Port("straight", "output", position=(75, 0), medium="fiber"),
        Port("turn", "output", position=(30, -75 if left else 75),
             medium="fiber", exit_direction=270 if left else 90),
    ), artwork_rotation=0 if left else 180, reflected=not left)


register_component(ComponentDefinition(
    "fiber_splitter", "Fiber splitter",
    Artwork((70, 60), (18, 8, 122, 62), 1.5,
            package_resource="f-fiber-splitter.svg",
            attribution="Original beampath schematic artwork for a 1x2 fiber splitter: "
                        "a continuous through fiber with a curved exit ending perpendicular to it, "
                        "based on the user's freeway-exit description."),
    _fiber_splitter))


def fiber_splitter(label: str | None = None, *, turn: str = "left"):
    """A continuous fiber with a curved branch ending at a perpendicular output.

    turn selects the side of the branch relative to its drawing pose.
    Select outputs with straight() and turn(), or out("straight"/"turn").
    A split ratio can be included in the label.
    """
    return component("fiber_splitter", label, turn=turn)


def demo():
    """Show fiber_splitter with its open beam or fiber ports."""
    from beampath import beam
    from beampath.components import fiber_splitter

    setup = beam() >> fiber_splitter()
    return setup
