"""The beamsplitter component and its minimal demonstration."""
from __future__ import annotations
from ..definitions import ComponentDefinition, Geometry, Port, component, register_component
from ..errors import ComponentError
from ._shared import _art, _parameters


def _splitter(parameters):
    _parameters(parameters, ("turn",))
    turn = parameters.get("turn", "left")
    if not isinstance(turn, str) or turn.lower() not in {"left", "right"}:
        raise ComponentError("Beamsplitter turn must be 'left' or 'right'")
    left = turn.lower() == "left"
    reflected = 270 if left else 90
    # The source cube reflects left; rotate it a quarter-turn to reflect right.
    return Geometry((Port("primary", "input"),
                     Port("secondary", "input", reflected, required=False),
                     Port("straight", "output"), Port("reflect", "output", reflected)),
                    artwork_rotation=0 if left else -90)


register_component(ComponentDefinition(
    "beamsplitter", "NPBS",
    _art("fs-npbs-cube.svg", "free-space-optics/flat_2d/svg/15_nonpolarizing",
         (60, 45), (39, 24, 81, 66), 1.6, source_filename="fs-bs-cube.svg"),
    _splitter, default_input="primary"))


def beamsplitter(label: str | None = None, *, turn: str = "left"):
    """A non-polarizing cube beamsplitter, labeled NPBS by default.

    turn selects a 90° reflection left (default) or right relative to the
    primary incoming beam. Select outputs with straight() and reflect().
    """
    return component("beamsplitter", label, turn=turn)


def demo():
    """Show beamsplitter with its open beam or fiber ports."""
    from beampath import beam
    from beampath.components import beamsplitter

    setup = beam() >> beamsplitter()
    return setup
