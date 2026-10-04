"""Declarative component geometry and reusable component specifications."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Mapping, Literal
import math

from .errors import ComponentError
from .geometry import Bounds, Point, finite, point


@dataclass(frozen=True)
class Port:
    """Heading of propagation, in the component's reference beam frame.

    Input headings point INTO the component, output headings point OUT.
    Positions are in diagram units relative to its placement origin.
    An absolute output direction uses the drawing's compass frame instead.
    draw_lead_in controls the incoming stub when an input starts a beam.
    Fiber ports have direction=None: exit_direction is only an outward drawing
    tangent for the cable router, relative to the component's layout rotation.
    draw_open controls unconnected output stubs (artwork may include a pigtail).
    """

    name: str
    kind: Literal["input", "output"]
    direction: float | None = 0
    position: Point = (0, 0)
    required: bool = True
    absolute: bool = False
    draw_lead_in: bool = True
    medium: Literal["free_space", "fiber"] = "free_space"
    exit_direction: float | None = None
    draw_open: bool = True

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name:
            raise ComponentError("A port must have a nonempty name")
        if self.kind not in {"input", "output"}:
            raise ComponentError(f"Invalid port kind {self.kind!r}")
        if self.absolute and self.kind != "output":
            raise ComponentError("Only output ports can have absolute headings")
        if not isinstance(self.draw_lead_in, bool):
            raise ComponentError("draw_lead_in must be a boolean")
        if self.medium not in {"free_space", "fiber"}:
            raise ComponentError("Port medium must be 'free_space' or 'fiber'")
        if not isinstance(self.draw_open, bool):
            raise ComponentError("draw_open must be a boolean")
        if self.medium == "fiber":
            if self.absolute:
                raise ComponentError("Fiber ports cannot have absolute optical headings")
            object.__setattr__(self, "direction", None)
            exit_direction = self.exit_direction
            if exit_direction is None:
                exit_direction = 180 if self.kind == "input" else 0
            object.__setattr__(self, "exit_direction", finite(exit_direction, "fiber exit direction") % 360)
        else:
            object.__setattr__(self, "direction", finite(self.direction, "port direction") % 360)
            if self.exit_direction is not None:
                raise ComponentError("exit_direction is a drawing hint for fiber ports only")
        object.__setattr__(self, "position", point(self.position, "port position"))


@dataclass(frozen=True)
class Geometry:
    """Local ports and artwork pose, relative to primary incidence.

    heading constrains a free-space frame; default_heading seeds an otherwise
    unconstrained frame after explicit constraints have propagated.
    """

    ports: tuple[Port, ...]
    artwork_rotation: float = 0
    reflected: bool = False
    heading: float | None = None
    default_heading: float | None = None

    def __post_init__(self):
        object.__setattr__(self, "ports", tuple(self.ports))
        if not self.ports or any(not isinstance(p, Port) for p in self.ports):
            raise ComponentError("Geometry must contain Port objects")
        names = [p.name for p in self.ports]
        if len(names) != len(set(names)):
            raise ComponentError("Port names must be unique within an optic")
        object.__setattr__(self, "artwork_rotation", finite(self.artwork_rotation, "artwork rotation"))
        for name in ("heading", "default_heading"):
            if getattr(self, name) is not None:
                if not any(p.medium == "free_space" for p in self.ports):
                    raise ComponentError("Only free-space geometry can constrain an optical heading")
                object.__setattr__(self, name, finite(getattr(self, name), name) % 360)


@dataclass(frozen=True)
class Artwork:
    """SVG artwork, optical anchor, conservative source bounds and credits.

    Supply exactly one of package_resource (for builtins), path, or svg.
    A selector can omit demonstrations and captions without changing the file.
    """

    center: Point
    bounds: Bounds
    scale: float = 1
    package_resource: str | None = None
    path: str | Path | None = None
    svg: str | None = None
    attribution: str = ""
    source_url: str = ""
    license_url: str = ""
    selector: Callable | None = field(default=None, repr=False, compare=False)

    def __post_init__(self):
        if sum(x is not None for x in (self.package_resource, self.path, self.svg)) != 1:
            raise ComponentError("Artwork needs exactly one SVG source")
        object.__setattr__(self, "center", point(self.center, "artwork center"))
        if len(self.bounds) != 4:
            raise ComponentError("Artwork bounds must contain four coordinates")
        bounds = tuple(finite(v, "artwork bounds") for v in self.bounds)
        if bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
            raise ComponentError("Artwork bounds must have positive area")
        object.__setattr__(self, "bounds", bounds)
        object.__setattr__(self, "scale", finite(self.scale, "artwork scale"))
        if self.scale <= 0:
            raise ComponentError("Artwork scale must be positive")


@dataclass(frozen=True)
class ComponentDefinition:
    """A geometry resolver, optionally refined once incidence is known.

    resolve_incidence receives the absolute reference-beam heading and must
    preserve port names, kinds, and input directions from resolve().
    """

    name: str
    default_label: str
    artwork: Artwork
    resolve: Callable[[Mapping], Geometry]
    default_input: str | None = "in"
    label_anchor: Point | None = None
    resolve_incidence: Callable[[Mapping, float], Geometry] | None = None

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name:
            raise ComponentError("A component definition needs a name")
        if not isinstance(self.artwork, Artwork):
            raise ComponentError("A definition needs Artwork")
        if not isinstance(self.default_label, str) or not callable(self.resolve):
            raise ComponentError("A definition needs a label and geometry resolver")
        if self.resolve_incidence is not None and not callable(self.resolve_incidence):
            raise ComponentError("An incidence resolver must be callable")
        if self.label_anchor is not None:
            object.__setattr__(self, "label_anchor", point(self.label_anchor, "label anchor"))


def _freeze(value):
    if isinstance(value, Mapping):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, (tuple, list)):
        return tuple(_freeze(v) for v in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze(v) for v in value)
    if value is None or isinstance(value, (str, bool, int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            raise ComponentError("Component parameters must be finite")
        return value
    raise ComponentError(f"Unsupported component parameter {type(value).__name__}")


@dataclass(frozen=True)
class ComponentSpec:
    """An immutable component template. Inserting it repeatedly creates independent physical optics."""
    definition: ComponentDefinition
    label: str | None = None
    parameters: Mapping = field(default_factory=dict)
    geometry: Geometry = field(init=False, repr=False)

    def __post_init__(self):
        if not isinstance(self.definition, ComponentDefinition):
            raise ComponentError("A specification needs a ComponentDefinition")
        if self.label is not None and not isinstance(self.label, str):
            raise ComponentError("Label must be a string or None")
        parameters = _freeze(self.parameters)
        object.__setattr__(self, "parameters", parameters)
        try:
            geometry = self.definition.resolve(parameters)
        except ComponentError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise ComponentError(f"{self.definition.name}: {exc}") from exc
        if not isinstance(geometry, Geometry):
            raise ComponentError("A component resolver must return Geometry")
        if self.definition.default_input is not None and not any(
            p.name == self.definition.default_input and p.kind == "input" for p in geometry.ports
        ):
            raise ComponentError(f"{self.definition.name}: default input does not exist")
        object.__setattr__(self, "geometry", geometry)

    @property
    def display_label(self) -> str:
        return self.definition.default_label if self.label is None else self.label

    def geometry_for_heading(self, heading: float) -> Geometry:
        """Resolve incidence-dependent geometry without changing this template."""
        if self.definition.resolve_incidence is None:
            return self.geometry
        try:
            geometry = self.definition.resolve_incidence(self.parameters, heading)
        except ComponentError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise ComponentError(f"{self.definition.name}: {exc}") from exc
        if not isinstance(geometry, Geometry):
            raise ComponentError("An incidence resolver must return Geometry")
        if {(p.name, p.kind, p.medium) for p in geometry.ports} != {
            (p.name, p.kind, p.medium) for p in self.geometry.ports
        }:
            raise ComponentError("An incidence resolver must preserve port names, kinds, and media")
        if {p.name: p.direction for p in geometry.ports if p.kind == "input"} != {
            p.name: p.direction for p in self.geometry.ports if p.kind == "input"
        }:
            raise ComponentError("An incidence resolver must preserve input directions")
        return geometry

    def __rshift__(self, other):
        from .model import beam
        return beam().append(self).append(other)


@dataclass(frozen=True)
class Chain:
    """A reusable sequence of component templates; each insertion creates independent optics."""
    specs: tuple[ComponentSpec, ...]

    def __post_init__(self):
        specs = tuple(self.specs)
        if not specs or any(not isinstance(s, ComponentSpec) for s in specs):
            raise ComponentError("A chain needs component specifications")
        object.__setattr__(self, "specs", specs)

    def __rshift__(self, other):
        from .model import beam
        return beam().append(self).append(other)


def chain(*specs: ComponentSpec | Chain) -> Chain:
    """Combine component specifications or existing chains into a reusable linear sequence."""
    items = []
    for spec in specs:
        if isinstance(spec, Chain):
            items.extend(spec.specs)
        elif isinstance(spec, ComponentSpec):
            items.append(spec)
        else:
            raise ComponentError("chain() accepts component specifications and chains")
    if not items:
        raise ComponentError("A chain must contain at least one component")
    return Chain(tuple(items))


_registry: dict[str, ComponentDefinition] = {}


def register_component(definition: ComponentDefinition) -> None:
    """Register a uniquely named component definition for use through component()."""
    if not isinstance(definition, ComponentDefinition):
        raise ComponentError("Expected a ComponentDefinition")
    if definition.name in _registry:
        raise ComponentError(f"Component {definition.name!r} is already registered")
    _registry[definition.name] = definition


def component(name: str, label: str | None = None, **parameters) -> ComponentSpec:
    """Create a specification from a registered component name, optional label, and component parameters."""
    try:
        definition = _registry[name]
    except KeyError as exc:
        raise ComponentError(f"Unknown component {name!r}") from exc
    return ComponentSpec(definition, label, parameters)
