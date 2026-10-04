"""Shared geometry helpers and pinned artwork provenance for builtin components."""
from ..definitions import Artwork, Geometry, Port
from ..errors import ComponentError
from ..geometry import heading


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


def _cube_splitter(parameters):
    _parameters(parameters, ("turn",))
    turn = parameters.get("turn", "left")
    if not isinstance(turn, str) or turn.lower() not in {"left", "right"}:
        raise ComponentError("Beamsplitter turn must be 'left' or 'right'")
    left = turn.lower() == "left"
    reflected = 270 if left else 90
    # The retained cube diagonal reflects left; rotate it for a right turn.
    return Geometry((Port("primary", "input"),
                     Port("secondary", "input", reflected, required=False),
                     Port("straight", "output"), Port("reflect", "output", reflected)),
                    artwork_rotation=0 if left else -90)


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


_FIBER_TRANSITION_ARTWORK = _art(
    "f-fiber-launch.svg", "fiber-optics/flat_2d/svg/11_beam_delivery",
    (46.5, 27), (41, 10, 111, 44), 2.4, remove_axes=True,
    adaptations="Embedded fiber tail removed; fiber connects at the housing.")
