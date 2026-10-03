"""Builtins using pinned PCL artwork and original schematic assets."""
from __future__ import annotations

import math

from .definitions import Artwork, ComponentDefinition, Geometry, Port, component, register_component
from .errors import ComponentError
from .geometry import aligned, finite, heading, reflection

__all__ = [
    "fiber_launch", "mirror", "beamsplitter", "iris", "LP", "HWP", "QWP", "noise_eater",
    "nd_filter", "bandpass_filter",
]

REVISION = "7e44e14341489b067d7c8e1390af87b9c423103e"
REPOSITORY = "https://github.com/itgall/photonics-component-library"
LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
ATTRIBUTION = (
    "Component artwork: Photonics Component Library (2025), Photonics Component Library "
    "Contributors, maintained by Isaac Gallegos (itgall). " + REPOSITORY + ". "
    "Licensed under Creative Commons Attribution 4.0 International (" + LICENSE_URL + "). "
    "Adaptations: source captions, demonstration beams and annotations removed; "
    "primitives uniformly scaled, translated, rotated or reflected; text kept upright; "
    "IDs namespaced; diagram beams and labels added. No endorsement is implied."
)


def _selector(*, remove_axes=False):
    def keep(element):
        tag = element.tag.rsplit("}", 1)[-1]
        if tag == "text":
            return False
        if tag == "line":
            if element.get("stroke") == "#CC0000" and not element.get("stroke-dasharray"):
                return False
            if remove_axes and element.get("stroke") == "#444444":
                return False
        return True
    return keep


def _art(filename, upstream_path, center, bounds, scale, *, remove_axes=False, source_filename=None):
    source_filename = source_filename or filename
    return Artwork(center, bounds, scale, package_resource=filename,
                   source_url=f"https://raw.githubusercontent.com/itgall/photonics-component-library/{REVISION}/{upstream_path}/{source_filename}",
                   attribution=ATTRIBUTION, license_url=LICENSE_URL,
                   selector=_selector(remove_axes=remove_axes))


def _parameters(parameters, allowed):
    extra = set(parameters) - set(allowed)
    if extra:
        raise ComponentError(f"Unknown component parameter(s): {', '.join(sorted(extra))}")


def _straight(parameters):
    _parameters(parameters, ())
    return Geometry((Port("in", "input"), Port("out", "output")))


def _fiber(parameters):
    _parameters(parameters, ("role",))
    role = parameters.get("role", "launch")
    if role not in {"launch", "couple"}:
        raise ComponentError("fiber_launch role must be 'launch' or 'couple'")
    ports = (Port("in", "input", draw_lead_in=role == "couple"),)
    if role == "launch":
        ports += (Port("out", "output"),)
    return Geometry(ports, reflected=role == "launch")


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


def _splitter(parameters):
    _parameters(parameters, ("angle",))
    angle = finite(parameters["angle"], "beamsplitter angle")
    reflected = reflection(0, angle)
    if aligned(reflected, 0) or aligned(reflected, 180):
        raise ComponentError("Beamsplitter angle must give four distinct physical ports")
    # The cube's splitting diagonal (40,65)..(80,25) has a 45-degree normal.
    source_normal = 45
    return Geometry((Port("primary", "input"),
                     Port("secondary", "input", reflected, required=False),
                     Port("straight", "output"), Port("reflect", "output", reflected)),
                    artwork_rotation=angle - source_normal)


register_component(ComponentDefinition(
    "fiber_launch", "Fiber launch",
    _art("f-fiber-launch.svg", "fiber-optics/flat_2d/svg/11_beam_delivery",
         (46.5, 27), (41, 10, 177, 44), 2.4, remove_axes=True),
    _fiber, label_anchor=(85, 27)))
register_component(ComponentDefinition(
    "mirror", "Mirror",
    _art("fs-flat-mirror.svg", "free-space-optics/flat_2d/svg/14_flat_mirrors",
         (62.5, 35), (46, 14, 76, 56), 1.6), _mirror,
    resolve_incidence=_mirror_incidence))
register_component(ComponentDefinition(
    "iris", "Iris",
    _art("fs-iris.svg", "free-space-optics/flat_2d/svg/23_apertures_beam_control",
         (50, 40), (24, 14, 76, 66), 1.5), _straight))
register_component(ComponentDefinition(
    "LP", "LP",
    _art("fs-wire-grid-polarizer.svg", "free-space-optics/flat_2d/svg/17_polarizers",
         (49, 35), (44, 7, 54, 63), 1.5), _straight))
for name in ("HWP", "QWP"):
    register_component(ComponentDefinition(
        name, name, _art(f"fs-{name.lower()}.svg", "free-space-optics/flat_2d/svg/17_waveplates",
                        (54, 35), (49, 9, 59, 61), 1.5), _straight))
register_component(ComponentDefinition(
    "nd_filter", "ND filter",
    _art("fs-nd-filter.svg", "free-space-optics/flat_2d/svg/18_nd_filters",
         (53, 35), (47, 9, 59, 61), 1.5), _straight))
register_component(ComponentDefinition(
    "bandpass_filter", "Bandpass filter",
    _art("fs-bandpass-filter.svg", "free-space-optics/flat_2d/svg/18_interference_filters",
         (53, 35), (47, 9, 59, 61), 1.5), _straight))
register_component(ComponentDefinition(
    "beamsplitter", "NPBS",
    _art("fs-npbs-cube.svg", "free-space-optics/flat_2d/svg/15_nonpolarizing",
         (60, 45), (39, 24, 81, 66), 1.6, source_filename="fs-bs-cube.svg"),
    _splitter, default_input="primary"))
register_component(ComponentDefinition(
    "noise_eater", "Noise eater",
    Artwork((54, 60), (30, 9, 68, 111), 1.5,
            package_resource="fs-noise-eater.svg",
            attribution="Original beampath schematic artwork for a Thorlabs NEL03A noise eater; "
                        "green housing based on the user-supplied Laser Clean-up diagram."),
    _straight))


def fiber_launch(label: str | None = None, *, role: str = "launch"):
    if label is None and role == "couple":
        label = "Fiber coupler"
    return component("fiber_launch", label, role=role)


def mirror(label: str | None = None, *, angle: float | None = None,
           heading: str | float | None = None, turn: str | None = None):
    """Reflect using a relative normal, absolute outbound heading, or 90° turn."""
    parameters = {name: value for name, value in
                  (("angle", angle), ("heading", heading), ("turn", turn))
                  if value is not None}
    return component("mirror", label, **parameters)


def beamsplitter(label: str | None = None, *, angle: float):
    """A non-polarizing cube beamsplitter, labeled NPBS by default."""
    return component("beamsplitter", label, angle=angle)


def iris(label: str | None = None):
    return component("iris", label)


def LP(label: str | None = None):
    return component("LP", label)


def HWP(label: str | None = None):
    return component("HWP", label)


def QWP(label: str | None = None):
    return component("QWP", label)


def nd_filter(label: str | None = None):
    """A straight-through free-space neutral-density filter."""
    return component("nd_filter", label)


def bandpass_filter(label: str | None = None):
    """A straight-through free-space bandpass filter."""
    return component("bandpass_filter", label)


def noise_eater(label: str | None = None):
    """A straight-through NEL03A noise-eater schematic with no control leads."""
    return component("noise_eater", label)
