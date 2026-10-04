"""The mirror component and its minimal demonstration."""
from __future__ import annotations

import math
from ..definitions import ComponentDefinition, Geometry, Port, component, register_component
from ..errors import ComponentError
from ..geometry import aligned, finite, heading, reflection
from ._shared import _art, _parameters


def _mirror(parameters):
    _parameters(parameters, ("angle", "heading", "turn"))
    if len(parameters) != 1:
        raise ComponentError("Mirror requires exactly one of angle, heading, or turn")
    if "heading" in parameters:
        # The outbound direction is fixed before incidence is known. The
        # instance resolver determines the local ports and artwork later.
        outgoing = heading(parameters["heading"])
        return Geometry((Port("in", "input"), Port("out", "output", outgoing, absolute=True)))
    if "turn" in parameters:
        turn = parameters["turn"]
        if not isinstance(turn, str) or turn.lower() not in {"left", "right"}:
            raise ComponentError("Mirror turn must be 'left' or 'right'")
        angle = 45 if turn.lower() == "left" else -45
    else:
        angle = finite(parameters["angle"], "mirror angle")
    return _mirror_geometry(angle)


def _mirror_geometry(angle):
    outgoing = reflection(0, angle)
    if aligned(outgoing, 0):
        raise ComponentError("Mirror cannot leave the beam heading unchanged (grazing incidence)")
    # Source hatching lies along the surface normal at tangent + 90 degrees.
    # Pick the equivalent normal whose backing points away from incidence.
    normal = (angle + 90) % 180 - 90
    tangent = math.degrees(math.atan2(40, 25))
    return Geometry((Port("in", "input"), Port("out", "output", outgoing)),
                    artwork_rotation=normal - (tangent + 90))


def _mirror_incidence(parameters, incoming):
    if "heading" not in parameters:
        return _mirror(parameters)
    outgoing = heading(parameters["heading"])
    angle = ((outgoing - incoming) % 360 - 180) / 2
    return _mirror_geometry(angle)


register_component(ComponentDefinition(
    "mirror", "Mirror",
    _art("fs-flat-mirror.svg", "free-space-optics/flat_2d/svg/14_flat_mirrors",
         (62.5, 35), (46, 14, 76, 56), 1.6), _mirror,
    resolve_incidence=_mirror_incidence))


def mirror(label: str | None = None, *, angle: float | None = None,
           heading: str | float | None = None, turn: str | None = None):
    """Reflect using exactly one of angle, heading, or turn.

    heading sets the absolute outbound direction. turn is a relative 90-degree
    left or right turn. angle sets the surface normal relative to incidence:
    angle=-45 turns an eastward beam south. Grazing incidence is invalid.
    """
    parameters = {name: value for name, value in
                  (("angle", angle), ("heading", heading), ("turn", turn))
                  if value is not None}
    return component("mirror", label, **parameters)


def demo():
    """Show mirror with its open beam or fiber ports."""
    from beampath import beam
    from beampath.components import mirror

    setup = beam() >> mirror(turn="left")
    return setup
