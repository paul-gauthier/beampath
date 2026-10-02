"""Builtins using the pinned Photonics Component Library artwork."""
from __future__ import annotations

import math

from .definitions import Artwork, ComponentDefinition, Geometry, Port, component, register_component
from .errors import ComponentError
from .geometry import aligned, finite, reflection

REVISION = "7e44e14341489b067d7c8e1390af87b9c423103e"
REPOSITORY = "https://github.com/itgall/photonics-component-library"
LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
ATTRIBUTION = (
    "Component artwork: Photonics Component Library (2025), Photonics Component Library "
    "Contributors, maintained by Isaac Gallegos (itgall). " + REPOSITORY + ". "
    "Licensed under Creative Commons Attribution 4.0 International (" + LICENSE_URL + "). "
    "Adaptations: source captions, demonstration beams and reference annotations removed; "
    "primitives uniformly scaled, translated, rotated or reflected; text kept upright; "
    "waveplate annotations resized and placed clear of the optics; "
    "IDs namespaced; diagram beams and labels added. No endorsement is implied."
)


def _selector(caption, *, annotations=(), remove_axes=False):
    def keep(element):
        tag = element.tag.rsplit("}", 1)[-1]
        if tag == "text" and element.text in (caption, *annotations):
            return False
        if tag == "line":
            if element.get("stroke") == "#CC0000" and not element.get("stroke-dasharray"):
                return False
            if remove_axes and element.get("stroke") == "#444444":
                return False
        return True
    return keep


def _art(filename, upstream_path, center, bounds, scale, caption, **selection):
    return Artwork(center, bounds, scale, package_resource=filename,
                   source_url=f"https://raw.githubusercontent.com/itgall/photonics-component-library/{REVISION}/{upstream_path}/{filename}",
                   attribution=ATTRIBUTION, license_url=LICENSE_URL,
                   selector=_selector(caption, **selection))


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
    ports = (Port("in", "input"),)
    if role == "launch":
        ports += (Port("out", "output"),)
    return Geometry(ports, reflected=role == "launch")


def _mirror(parameters):
    _parameters(parameters, ("angle",))
    angle = finite(parameters["angle"], "mirror angle")
    # Source hatching lies along the surface normal at tangent + 90 degrees.
    # Pick the equivalent normal whose backing points away from incidence.
    normal = (angle + 90) % 180 - 90
    tangent = math.degrees(math.atan2(40, 25))
    return Geometry((Port("in", "input"), Port("out", "output", reflection(0, angle))),
                    artwork_rotation=normal - (tangent + 90))


def _splitter(parameters):
    _parameters(parameters, ("angle",))
    angle = finite(parameters["angle"], "beamsplitter angle")
    reflected = reflection(0, angle)
    if aligned(reflected, 0) or aligned(reflected, 180):
        raise ComponentError("Beamsplitter angle must give four distinct physical ports")
    # Anchor is the midpoint of the upstream plate face (52,12)..(77,68).
    source_normal = math.degrees(math.atan2(56, 25)) - 90
    return Geometry((Port("primary", "input"),
                     Port("secondary", "input", reflected, required=False),
                     Port("straight", "output"), Port("reflect", "output", reflected)),
                    artwork_rotation=angle - source_normal)


register_component(ComponentDefinition(
    "fiber_launch", "Fiber launch",
    _art("f-fiber-launch.svg", "fiber-optics/flat_2d/svg/11_beam_delivery",
         (46.5, 27), (41, 10, 177, 44), 2.4, "Fiber launch",
         annotations=("stage", "x", "y"), remove_axes=True),
    _fiber, label_anchor=(85, 27)))
register_component(ComponentDefinition(
    "mirror", "Mirror",
    _art("fs-flat-mirror.svg", "free-space-optics/flat_2d/svg/14_flat_mirrors",
         (62.5, 35), (46, 14, 76, 56), 1.6, "Flat mirror"), _mirror))
register_component(ComponentDefinition(
    "iris", "Iris",
    _art("fs-iris.svg", "free-space-optics/flat_2d/svg/23_apertures_beam_control",
         (50, 40), (24, 14, 76, 66), 1.5, "Iris diaphragm"), _straight))
register_component(ComponentDefinition(
    "LP", "LP",
    _art("fs-wire-grid-polarizer.svg", "free-space-optics/flat_2d/svg/17_polarizers",
         (49, 35), (44, 7, 54, 63), 1.5, "Wire-grid polarizer"), _straight))
for name, filename, caption, marking in (
    ("HWP", "fs-hwp.svg", "Half-wave plate", "λ/2"),
    ("QWP", "fs-qwp.svg", "Quarter-wave plate", "λ/4"),
):
    register_component(ComponentDefinition(
        name, name, _art(filename, "free-space-optics/flat_2d/svg/17_waveplates",
                        (54, 35), (49, 9, 59, 61), 1.5, caption,
                        annotations=(marking,)), _straight, marking=marking))
register_component(ComponentDefinition(
    "beamsplitter", "BS",
    _art("fs-bs-plate.svg", "free-space-optics/flat_2d/svg/15_nonpolarizing",
         (64.5, 40), (51, 11, 83, 69), 1.6, "Plate BS (50:50)", annotations=("in", "R", "T")),
    _splitter, default_input="primary"))


def fiber_launch(label: str | None = None, *, role: str = "launch"):
    if label is None and role == "couple":
        label = "Fiber coupler"
    return component("fiber_launch", label, role=role)


def mirror(label: str | None = None, *, angle: float):
    return component("mirror", label, angle=angle)


def beamsplitter(label: str | None = None, *, angle: float):
    return component("beamsplitter", label, angle=angle)


def iris(label: str | None = None):
    return component("iris", label)


def LP(label: str | None = None):
    return component("LP", label)


def HWP(label: str | None = None):
    return component("HWP", label)


def QWP(label: str | None = None):
    return component("QWP", label)
