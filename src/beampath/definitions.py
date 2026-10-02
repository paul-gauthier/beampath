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
    """

    name: str
    kind: Literal["input", "output"]
    direction: float = 0
    position: Point = (0, 0)
    required: bool = True

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name:
            raise ComponentError("A port must have a nonempty name")
        if self.kind not in {"input", "output"}:
            raise ComponentError(f"Invalid port kind {self.kind!r}")
        object.__setattr__(self, "direction", finite(self.direction, "port direction") % 360)
        object.__setattr__(self, "position", point(self.position, "port position"))


@dataclass(frozen=True)
class Geometry:
    """Resolved local ports and artwork pose, relative to primary incidence."""

    ports: tuple[Port, ...]
    artwork_rotation: float = 0
    reflected: bool = False

    def __post_init__(self):
        object.__setattr__(self, "ports", tuple(self.ports))
        if not self.ports or any(not isinstance(p, Port) for p in self.ports):
            raise ComponentError("Geometry must contain Port objects")
        names = [p.name for p in self.ports]
        if len(names) != len(set(names)):
            raise ComponentError("Port names must be unique within an optic")
        object.__setattr__(self, "artwork_rotation", finite(self.artwork_rotation, "artwork rotation"))


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
    name: str
    default_label: str
    artwork: Artwork
    resolve: Callable[[Mapping], Geometry]
    default_input: str | None = "in"
    label_anchor: Point | None = None
    marking: str | None = None

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name:
            raise ComponentError("A component definition needs a name")
        if not isinstance(self.artwork, Artwork):
            raise ComponentError("A definition needs Artwork")
        if not isinstance(self.default_label, str) or not callable(self.resolve):
            raise ComponentError("A definition needs a label and geometry resolver")
        if self.label_anchor is not None:
            object.__setattr__(self, "label_anchor", point(self.label_anchor, "label anchor"))
        if self.marking is not None and (not isinstance(self.marking, str) or not self.marking):
            raise ComponentError("A component marking must be a nonempty string")


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

    def __rshift__(self, other):
        from .model import beam
        return beam().append(self).append(other)


@dataclass(frozen=True)
class Chain:
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
    if not isinstance(definition, ComponentDefinition):
        raise ComponentError("Expected a ComponentDefinition")
    if definition.name in _registry:
        raise ComponentError(f"Component {definition.name!r} is already registered")
    _registry[definition.name] = definition


def component(name: str, label: str | None = None, **parameters) -> ComponentSpec:
    try:
        definition = _registry[name]
    except KeyError as exc:
        raise ComponentError(f"Unknown component {name!r}") from exc
    return ComponentSpec(definition, label, parameters)
