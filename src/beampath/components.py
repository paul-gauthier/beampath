"""Builtins using pinned PCL artwork and original schematic assets."""
from __future__ import annotations

import math

from .definitions import Artwork, ComponentDefinition, Geometry, Port, component, register_component
from .errors import ComponentError
from .geometry import aligned, finite, heading, reflection

__all__ = [
    "fiber_launch", "fiber_coupler", "mirror", "beamsplitter", "iris", "LP", "HWP", "QWP", "noise_eater",
    "nd_filter", "bandpass_filter", "fiber_laser", "inline_power_meter", "fiber_splitter",
    "fiber_power_meter", "spdc", "detector", "beam_block",
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
            return element.get("data-display-readout") == "true"
        if tag == "polygon" and element.get("fill") == "#CC0000":
            return False
        if tag == "line":
            if element.get("stroke") == "#CC0000" and not element.get("stroke-dasharray"):
                return False
            if remove_axes and element.get("stroke") == "#444444":
                return False
        return True
    return keep


def _art(filename, upstream_path, center, bounds, scale, *, remove_axes=False, source_filename=None,
         adaptations=""):
    source_filename = source_filename or filename
    return Artwork(center, bounds, scale, package_resource=filename,
                   source_url=f"https://raw.githubusercontent.com/itgall/photonics-component-library/{REVISION}/{upstream_path}/{source_filename}",
                   attribution=ATTRIBUTION + (" " + adaptations if adaptations else ""),
                   license_url=LICENSE_URL,
                   selector=_selector(remove_axes=remove_axes))


def _parameters(parameters, allowed):
    extra = set(parameters) - set(allowed)
    if extra:
        raise ComponentError(f"Unknown component parameter(s): {', '.join(sorted(extra))}")


def _straight(parameters):
    _parameters(parameters, ())
    return Geometry((Port("in", "input"), Port("out", "output")))


def _detector(parameters):
    _parameters(parameters, ())
    return Geometry((Port("in", "input", position=(-22, 0)),))


def _beam_block(parameters):
    _parameters(parameters, ())
    return Geometry((Port("in", "input", position=(-10, 0)),))


def _fiber_transition(parameters, *, launch):
    _parameters(parameters, ("heading",))
    if launch:
        ports = (Port("in", "input", position=(-152.4, 0), medium="fiber"),
                 Port("out", "output"))
    else:
        ports = (Port("in", "input"),
                 Port("out", "output", position=(152.4, 0), medium="fiber"))
    return Geometry(ports, reflected=launch,
                    heading=heading(parameters["heading"]) if "heading" in parameters else None,
                    default_heading=0 if launch else None)


def _fiber_launch(parameters):
    return _fiber_transition(parameters, launch=True)


def _fiber_coupler(parameters):
    return _fiber_transition(parameters, launch=False)


def _fiber_source(parameters):
    _parameters(parameters, ())
    return Geometry((Port("out", "output", position=(75, 0), medium="fiber"),))


def _fiber_meter(parameters):
    _parameters(parameters, ())
    return Geometry((Port("in", "input", medium="fiber"),
                     Port("out", "output", medium="fiber")))


def _fiber_sink(parameters):
    _parameters(parameters, ())
    return Geometry((Port("in", "input", position=(-41.25, 0), medium="fiber"),))


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


_FIBER_TRANSITION_ARTWORK = _art(
    "f-fiber-launch.svg", "fiber-optics/flat_2d/svg/11_beam_delivery",
    (46.5, 27), (41, 10, 111, 44), 2.4, remove_axes=True,
    adaptations="Embedded fiber tail removed; fiber connects at the housing.")
register_component(ComponentDefinition(
    "fiber_launch", "Fiber launch", _FIBER_TRANSITION_ARTWORK,
    _fiber_launch, label_anchor=(85, 27)))
register_component(ComponentDefinition(
    "fiber_coupler", "Fiber coupler", _FIBER_TRANSITION_ARTWORK,
    _fiber_coupler, label_anchor=(85, 27)))
register_component(ComponentDefinition(
    "fiber_laser", "Fiber laser",
    _art("f-laser.svg", "fiber-optics/flat_2d/svg/05_laser_sources",
         (65, 32), (14, 11, 116, 53), 1.5,
         adaptations="Embedded fiber tail removed; fiber connects at the housing."),
    _fiber_source, default_input=None))
register_component(ComponentDefinition(
    "inline_power_meter", "Inline power meter",
    _art("f-inline-power-meter.svg", "fiber-optics/flat_2d/svg/11_inline_components",
         (85, 27), (56.5, 25, 113.5, 79), 1.5,
         adaptations="Housing and display match the standalone f-power-meter.svg at the same scale. "
                     "Inline power-meter display changed to 1.23 mW and kept aligned with its housing. "
                     "Embedded through fiber removed; both fiber ports attach at the tap. "
                     "Internal tap fiber matches the routed fiber style."),
    _fiber_meter))
register_component(ComponentDefinition(
    "fiber_power_meter", "Fiber power meter",
    _art("f-power-meter.svg", "fiber-optics/flat_2d/svg/10_test_equipment",
         (57.5, 27), (29, 7, 86, 47), 1.5,
         adaptations="Display readout retained aligned with its housing. "
                     "Embedded fiber line removed; fiber connects at the housing input."),
    _fiber_sink))
register_component(ComponentDefinition(
    "fiber_splitter", "Fiber splitter",
    Artwork((70, 60), (18, 8, 122, 62), 1.5,
            package_resource="f-fiber-splitter.svg",
            attribution="Original beampath schematic artwork for a 1x2 fiber splitter: "
                        "a continuous through fiber with a curved exit ending perpendicular to it, "
                        "based on the user's freeway-exit description."),
    _fiber_splitter))
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
    "detector", "Detector",
    Artwork((0, 0), (-24, -30, 38, 30),
            package_resource="fs-detector.svg",
            attribution="Original beampath schematic artwork for a detector: "
                        "a blue D-shaped housing with a flat beam-entry face."),
    _detector))
register_component(ComponentDefinition(
    "beam_block", "Beam block",
    Artwork((0, 0), (-12, -30, 12, 30),
            package_resource="fs-beam-block.svg",
            attribution="Original beampath schematic artwork for a beam block: "
                        "a dark rectangular absorber."),
    _beam_block))
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
    "spdc", "SPDC",
    _art("fs-spdc.svg", "free-space-optics/flat_2d/svg/31_quantum_sources",
         (75.5, 37), (57.5, 13.5, 93.5, 60.5), 1.5,
         source_filename="fs-spdc-type1.svg",
         adaptations="Only the crystal body is retained; BBO, Type I, source captions, "
                     "and all demonstration beams are removed. Pump, signal, and idler "
                     "paths are generated from the component ports."),
    _spdc))
register_component(ComponentDefinition(
    "noise_eater", "Noise eater",
    Artwork((54, 60), (30, 9, 68, 111), 1.5,
            package_resource="fs-noise-eater.svg",
            attribution="Original beampath schematic artwork for a Thorlabs NEL03A noise eater; "
                        "green housing based on the user-supplied Laser Clean-up diagram."),
    _straight))


def fiber_launch(label: str | None = None, *, heading: str | float | None = None):
    """Convert fiber to free space, defaulting to an eastward beam heading."""
    parameters = {}
    if heading is not None:
        parameters["heading"] = heading
    return component("fiber_launch", label, **parameters)


def fiber_coupler(label: str | None = None, *, heading: str | float | None = None):
    """Convert free space to fiber, following the incoming beam heading."""
    parameters = {}
    if heading is not None:
        parameters["heading"] = heading
    return component("fiber_coupler", label, **parameters)


def fiber_laser(label: str | None = None):
    """A source with a fiber output and no optical heading."""
    return component("fiber_laser", label)


def inline_power_meter(label: str | None = None):
    """A power monitor through which the fiber path continues."""
    return component("inline_power_meter", label)


def fiber_power_meter(label: str | None = None):
    """A power meter with a single fiber input that ends the path."""
    return component("fiber_power_meter", label)


def fiber_splitter(label: str | None = None, *, turn: str = "left"):
    """A continuous fiber with a curved branch ending at a perpendicular output.

    turn selects the side of the branch relative to its drawing pose.
    Select outputs with straight() and turn(), or out("straight"/"turn").
    A split ratio can be included in the label; optical power is not simulated.
    """
    return component("fiber_splitter", label, turn=turn)


def mirror(label: str | None = None, *, angle: float | None = None,
           heading: str | float | None = None, turn: str | None = None):
    """Reflect using a relative normal, absolute outbound heading, or 90° turn."""
    parameters = {name: value for name, value in
                  (("angle", angle), ("heading", heading), ("turn", turn))
                  if value is not None}
    return component("mirror", label, **parameters)


def beamsplitter(label: str | None = None, *, turn: str = "left"):
    """A non-polarizing cube beamsplitter, labeled NPBS by default.

    turn selects a 90° reflection left (default) or right relative to the
    primary incoming beam. Select outputs with straight() and reflect().
    """
    return component("beamsplitter", label, turn=turn)


def spdc(label: str | None = None, *, opening_angle: float = 20):
    """A generic SPDC crystal with pump, signal, and idler output ports.

    opening_angle is the full signal-idler angle in degrees, from 0 to 180.
    The pump continues straight; signal and idler turn by -/+ half the angle.
    Zero makes all three outputs collinear, retaining their distinct names.
    Select a path with out("pump"), out("signal"), or out("idler").
    The default input "in" is the required pump. Optional "signal_in" and
    "idler_in" inputs continue along their corresponding output rays; use
    path.connect(crystal.input("idler_in")) to overlap an incoming idler.
    Unconnected optional inputs are not drawn. Overlap is geometrical only.
    Crystal material and polarization type belong in the optional label.
    """
    return component("spdc", label, opening_angle=opening_angle)


def iris(label: str | None = None):
    return component("iris", label)


def detector(label: str | None = None):
    """A generic detector with one free-space input that ends the beam path.

    The flat face follows the incoming beam. Detector type (such as a
    single-photon detector) belongs in the label; detection is not simulated.
    """
    return component("detector", label)


def beam_block(label: str | None = None):
    """A beam block with one free-space input and no output, following incidence."""
    return component("beam_block", label)


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
