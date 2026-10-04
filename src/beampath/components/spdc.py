"""The spdc component and its minimal demonstration."""
from __future__ import annotations
from ..definitions import ComponentDefinition, Geometry, Port, component, register_component
from ..errors import ComponentError
from ..geometry import finite
from ._shared import _art, _parameters


def _spdc(parameters):
    _parameters(parameters, ("opening_angle",))
    angle = finite(parameters.get("opening_angle", 20), "SPDC opening_angle")
    if not 0 <= angle <= 180:
        raise ComponentError("SPDC opening_angle must be between 0 and 180 degrees")
    return Geometry((Port("in", "input"), Port("pump", "output"),
                     Port("signal", "output", -angle / 2),
                     Port("idler", "output", angle / 2),
                     Port("signal_in", "input", -angle / 2, required=False),
                     Port("idler_in", "input", angle / 2, required=False)))


register_component(ComponentDefinition(
    "spdc", "SPDC",
    _art("fs-spdc.svg", "free-space-optics/flat_2d/svg/31_quantum_sources",
         (75.5, 37), (57.5, 13.5, 93.5, 60.5), 1.5,
         source_filename="fs-spdc-type1.svg",
         adaptations="Only the crystal body is retained; BBO, Type I, source captions, "
                     "and all demonstration beams are removed. Pump, signal, and idler "
                     "paths are generated from the component ports."),
    _spdc))


def spdc(label: str | None = None, *, opening_angle: float = 20):
    """A generic SPDC crystal with pump, signal, and idler output ports.

    opening_angle is the full signal-idler angle in degrees, from 0 to 180.
    The pump continues straight; signal and idler turn by -/+ half the angle.
    Zero makes all three outputs collinear, retaining their distinct names.
    Select a path with out("pump"), out("signal"), or out("idler").
    The default input "in" is the required pump. Optional "signal_in" and
    "idler_in" inputs continue along their corresponding output rays; use
    path.connect(crystal.input("idler_in")) to overlap an incoming idler.
    Unconnected optional inputs are not drawn.
    Crystal material and polarization type belong in the optional label.
    """
    return component("spdc", label, opening_angle=opening_angle)


def demo():
    """Show spdc with its open beam or fiber ports."""
    from beampath import beam
    from beampath.components import spdc

    setup = beam() >> spdc()
    return setup
