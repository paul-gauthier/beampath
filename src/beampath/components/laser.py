"""The laser component and its minimal demonstration."""
from __future__ import annotations
from ..definitions import ComponentDefinition, Geometry, Port, component, register_component
from ._shared import _art, _parameters


def _laser(parameters):
    _parameters(parameters, ())
    return Geometry((Port("out", "output", position=(60, 0)),))


register_component(ComponentDefinition(
    "laser", "Laser",
    _art("fs-diode-laser.svg", "free-space-optics/flat_2d/svg/26_semiconductor_lasers",
         (45, 26), (14.5, 11.5, 85.5, 40.5), 1.5,
         adaptations="Only the diode-laser housing and nozzle are retained; electrical "
                     "leads, type text, caption, and demonstration beam removed."),
    _laser, default_input=None))


def laser(label: str | None = None):
    """A generic laser with one free-space output and no input.

    The beam starts at the nozzle. Set its direction with beam(direction=...).
    Laser type and wavelength belong in the label.
    """
    return component("laser", label)


def demo():
    """Show laser with its open beam port."""
    from beampath import beam
    from beampath.components import laser

    setup = beam() >> laser()
    return setup
