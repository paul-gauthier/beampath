"""The polarizing cube beamsplitter and its minimal demonstration."""
from __future__ import annotations

from ..definitions import ComponentDefinition, component, register_component
from ._shared import _art, _cube_splitter


register_component(ComponentDefinition(
    "PBS", "PBS",
    _art("fs-pbs-cube.svg", "free-space-optics/flat_2d/svg/15_polarizing",
         (60, 45), (39, 24, 81, 66), 1.6),
    _cube_splitter, default_input="primary"))


def PBS(label: str | None = None, *lines: str, turn: str = "left"):
    """A polarizing cube beamsplitter, labeled PBS by default.

    The cube transmits p polarization and reflects s polarization. For the
    primary input, straight() selects transmission and reflect() selects
    the orthogonal output, 90° left (default) or right according to turn.
    Inputs are "primary" (required and default) and "secondary" (optional).
    Use join() or connect() to combine two incoming paths at one cube.

    Output names describe geometry relative to primary incidence: for the
    secondary input, transmission exits reflect and reflection exits straight.
    They are not universal H/V labels when both inputs are occupied. Polarization
    conventions are descriptive; beampath does not simulate polarization.

    Use optic.reverse() for the same cube viewed from the opposite direction.
    Its default input receives a returning beam from the forward straight arm.
    Its reflect() exits opposite the forward reflected output; its straight()
    returns toward the source. Output names remain relative to that view's
    primary input, including when connecting its secondary input.
    """
    return component("PBS", label, *lines, turn=turn)


def demo():
    """Show a PBS with its primary input and two open outputs."""
    from beampath import beam
    from beampath.components import PBS

    setup = beam() >> PBS()
    return setup
