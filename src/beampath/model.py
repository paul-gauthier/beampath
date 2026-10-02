"""Physical optical graph and the mutable path-building DSL."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path as FilePath
from typing import TYPE_CHECKING

from .definitions import Chain, ComponentSpec, Port
from .errors import ConnectionError
from .geometry import Point, aligned, finite, heading, point

if TYPE_CHECKING:
    from .layout import Layout, Style


@dataclass(frozen=True)
class OpticInstance:
    id: str
    spec: ComponentSpec
    heading: float | None = None
    at: Point | None = None

    def port(self, name: str, kind: str | None = None) -> Port:
        for port in self.spec.geometry.ports:
            if port.name == name and (kind is None or port.kind == kind):
                return port
        raise ConnectionError(f"{self.id} ({self.spec.display_label}): no {kind or ''} port {name!r}")


@dataclass(frozen=True)
class Connection:
    id: str
    source: str
    output: str
    target: str
    input: str
    distance: float | None = None


@dataclass(frozen=True)
class Root:
    optic: str
    input: str | None
    direction: float
    origin: Point


@dataclass(frozen=True)
class InputRef:
    optic: OpticRef
    name: str


@dataclass(frozen=True)
class OpticRef:
    setup: Setup
    id: str

    @property
    def instance(self) -> OpticInstance:
        return self.setup._nodes[self.id]

    def input(self, name: str | None = None) -> InputRef:
        name = name if name is not None else self.instance.spec.definition.default_input
        if name is None:
            raise ConnectionError(f"{self.id}: this optic has no default input")
        self.instance.port(name, "input")
        return InputRef(self, name)

    def out(self, name: str) -> Path:
        self.instance.port(name, "output")
        if self.setup._output_used(self.id, name):
            raise ConnectionError(f"{self.id}.{name}: output is already connected")
        return Path(self.setup, self.id, name)

    def straight(self) -> Path:
        return self.out("straight")

    def reflect(self) -> Path:
        return self.out("reflect")


class Setup:
    """An owned graph. Public views are immutable; editing uses paths or refs."""

    def __init__(self):
        self._nodes: dict[str, OpticInstance] = {}
        self._connections: list[Connection] = []
        self._roots: list[Root] = []

    @property
    def optics(self) -> tuple[OpticInstance, ...]:
        return tuple(self._nodes.values())

    @property
    def connections(self) -> tuple[Connection, ...]:
        return tuple(self._connections)

    @contextmanager
    def _transaction(self):
        snapshot = self._nodes.copy(), self._connections.copy(), self._roots.copy()
        try:
            yield
        except Exception:
            self._nodes, self._connections, self._roots = snapshot
            raise

    def beam(self, direction: str | float = "east", *, origin: Point = (0, 0)) -> Path:
        return Path(self, initial_heading=heading(direction), origin=point(origin))

    def add(self, spec: ComponentSpec, *, at: Point | None = None) -> OpticRef:
        if not isinstance(spec, ComponentSpec):
            raise ConnectionError("add() needs a component specification")
        at = point(at) if at is not None else None
        ident = f"optic-{len(self._nodes) + 1:03d}"
        self._nodes[ident] = OpticInstance(ident, spec, at=at)
        return OpticRef(self, ident)

    def _output_used(self, optic: str, port: str) -> bool:
        return any(c.source == optic and c.output == port for c in self._connections)

    def _input_used(self, optic: str, port: str) -> bool:
        return (any(c.target == optic and c.input == port for c in self._connections)
                or any(r.optic == optic and r.input == port for r in self._roots))

    def _connect(self, source: str, output: str, target: str, input_name: str,
                 distance: float | None):
        self._nodes[source].port(output, "output")
        self._nodes[target].port(input_name, "input")
        if self._output_used(source, output):
            raise ConnectionError(f"{source}.{output}: output is already connected")
        if self._input_used(target, input_name):
            raise ConnectionError(f"{target}.{input_name}: input is already connected")
        reachable, todo = set(), [target]
        while todo:
            node = todo.pop()
            if node == source:
                raise ConnectionError(f"{target}.{input_name}: closed paths are not supported")
            if node not in reachable:
                reachable.add(node)
                todo.extend(c.target for c in self._connections if c.source == node)
        self._connections.append(Connection(f"segment-{len(self._connections) + 1:03d}",
                                            source, output, target, input_name, distance))
        self._resolve_headings()

    def _bind_root(self, optic: str, input_name: str | None, direction: float, origin: Point):
        if input_name is not None and self._input_used(optic, input_name):
            raise ConnectionError(f"{optic}.{input_name}: input is already connected")
        if any(r.optic == optic and r.input == input_name for r in self._roots):
            raise ConnectionError(f"{optic}: port already starts a beam")
        self._roots.append(Root(optic, input_name, direction, origin))
        self._resolve_headings()

    def _resolve_headings(self):
        # Propagate frame relations in both directions. A secondary input may be
        # connected first; it still refers to the same primary-relative frame.
        headings: dict[str, float] = {}
        todo: list[str] = []

        def assign(ident: str, value: float, context: str):
            value %= 360
            if ident in headings:
                if not aligned(headings[ident], value):
                    raise ConnectionError(f"{context}: incoming direction disagrees with optic orientation")
            else:
                headings[ident] = value
                todo.append(ident)

        for root in self._roots:
            offset = self._nodes[root.optic].port(root.input, "input").direction if root.input else 0
            assign(root.optic, root.direction - offset, root.optic)
        adjacency: dict[str, list[Connection]] = {ident: [] for ident in self._nodes}
        for edge in self._connections:
            adjacency[edge.source].append(edge)
            adjacency[edge.target].append(edge)
        while todo:
            ident = todo.pop(0)
            for edge in adjacency[ident]:
                outgoing = self._nodes[edge.source].port(edge.output).direction
                incoming = self._nodes[edge.target].port(edge.input).direction
                if ident == edge.source:
                    assign(edge.target, headings[ident] + outgoing - incoming,
                           f"{edge.target}.{edge.input}")
                else:
                    assign(edge.source, headings[ident] + incoming - outgoing,
                           f"{edge.source}.{edge.output}")
        self._nodes = {ident: replace(node, heading=headings.get(ident))
                       for ident, node in self._nodes.items()}

    def layout(self, *, style: Style | None = None) -> Layout:
        from .layout import layout
        return layout(self, style=style)

    def to_svg(self, *, style: Style | None = None) -> str:
        from .render import render_svg
        return render_svg(self.layout(style=style))

    def save(self, filename: str | FilePath, *, style: Style | None = None,
             width: int | None = None, dpi: float = 96) -> FilePath:
        from .render import save
        return save(self, filename, style=style, width=width, dpi=dpi)


def _distance(value: float | None) -> float | None:
    if value is None:
        return None
    value = finite(value, "distance")
    if value <= 0:
        raise ConnectionError("Distance must be positive")
    return value


class Path:
    """A mutable cursor in a Setup, either at an output or an output group."""

    def __init__(self, setup: Setup, end: str | None = None, port: str | None = None,
                 *, initial_heading: float = 0, origin: Point = (0, 0)):
        self.setup = setup
        self._end = end
        self._port = port
        self._initial_heading = initial_heading
        self._origin = origin
        self._consumed = False

    def _check(self):
        if self._consumed:
            raise ConnectionError("This path was consumed by a connection or join; select an outbound path")

    @property
    def end(self) -> OpticRef:
        if self._end is None:
            raise ConnectionError("This path has no first component yet")
        return OpticRef(self.setup, self._end)

    def _frontier(self) -> tuple[str, str]:
        self._check()
        if self._end is None:
            raise ConnectionError("This operation needs a component on the path")
        if self._port is None:
            outputs = [p for p in self.end.instance.spec.geometry.ports if p.kind == "output"]
            if outputs:
                raise ConnectionError(f"{self._end}: select an output with out(), straight(), or reflect()")
            raise ConnectionError(f"{self._end}: this component ends the beam path")
        if self.setup._output_used(self._end, self._port):
            raise ConnectionError(f"{self._end}.{self._port}: output is already connected")
        return self._end, self._port

    def append(self, spec: ComponentSpec | Chain, *, distance: float | None = None,
               at: Point | None = None) -> Path:
        self._check()
        if not isinstance(spec, (ComponentSpec, Chain)):
            raise ConnectionError("append() needs a component specification or chain")
        distance = _distance(distance)
        at = point(at) if at is not None else None
        specs = spec.specs if isinstance(spec, Chain) else (spec,)
        old_cursor = self._end, self._port
        try:
            with self.setup._transaction():
                for index, item in enumerate(specs):
                    self._append_one(item, distance if index == 0 else None,
                                     at if index == 0 else None)
        except Exception:
            self._end, self._port = old_cursor
            raise
        return self

    def _append_one(self, spec: ComponentSpec, distance: float | None, at: Point | None):
        frontier = self._frontier() if self._end is not None else None
        if frontier is None and distance is not None:
            raise ConnectionError("The first component has no preceding segment to set a distance on")
        ref = self.setup.add(spec, at=at)
        default_input = spec.definition.default_input
        if frontier is None:
            self.setup._bind_root(ref.id, default_input, self._initial_heading,
                                  at if at is not None else self._origin)
        elif default_input is None:
            raise ConnectionError(f"{ref.id}: cannot append an optic without an input")
        else:
            self.setup._connect(*frontier, ref.id, default_input, distance)
        outputs = [p.name for p in spec.geometry.ports if p.kind == "output"]
        self._end, self._port = ref.id, outputs[0] if len(outputs) == 1 else None

    def __rshift__(self, spec):
        return self.append(spec)

    def __irshift__(self, spec):
        return self.append(spec)

    def out(self, name: str) -> Path:
        self._check()
        return self.end.out(name)

    def straight(self) -> Path:
        return self.out("straight")

    def reflect(self) -> Path:
        return self.out("reflect")

    def connect(self, target: InputRef, *, distance: float | None = None) -> OpticRef:
        self._check()
        if not isinstance(target, InputRef):
            raise ConnectionError("connect() needs an optic.input(name) reference")
        if target.optic.setup is not self.setup:
            raise ConnectionError("Cannot connect paths from different setups")
        distance = _distance(distance)
        with self.setup._transaction():
            if self._end is None:
                if distance is not None:
                    raise ConnectionError("An initial beam has no preceding segment")
                self.setup._bind_root(target.optic.id, target.name, self._initial_heading,
                                      target.optic.instance.at or self._origin)
            else:
                self.setup._connect(*self._frontier(), target.optic.id, target.name, distance)
        self._consumed = True
        return target.optic

    def join(self, other: Path, spec: ComponentSpec, *, at: Point | None = None) -> Path:
        self._check()
        if not isinstance(other, Path) or other.setup is not self.setup:
            raise ConnectionError("Joined paths must belong to the same setup")
        other._check()
        if self is other:
            raise ConnectionError("Cannot join a path to itself")
        if not isinstance(spec, ComponentSpec):
            raise ConnectionError("join() needs a component specification")
        inputs = [p.name for p in spec.geometry.ports if p.kind == "input"]
        primary = spec.definition.default_input
        if len(inputs) != 2 or primary not in inputs:
            raise ConnectionError("join() needs an optic with two inputs and a default input")
        secondary = next(name for name in inputs if name != primary)
        a, b = self._frontier(), other._frontier()
        with self.setup._transaction():
            ref = self.setup.add(spec, at=at)
            self.setup._connect(*a, ref.id, primary, None)
            self.setup._connect(*b, ref.id, secondary, None)
        self._consumed = other._consumed = True
        outputs = [p.name for p in spec.geometry.ports if p.kind == "output"]
        return Path(self.setup, ref.id, outputs[0] if len(outputs) == 1 else None)

    def layout(self, **kwargs) -> Layout:
        return self.setup.layout(**kwargs)

    def to_svg(self, **kwargs) -> str:
        return self.setup.to_svg(**kwargs)

    def save(self, filename, **kwargs) -> FilePath:
        return self.setup.save(filename, **kwargs)


def beam(direction: str | float = "east", *, origin: Point = (0, 0)) -> Path:
    """Start a new setup without drawing an initial source or lead-in gap."""
    return Setup().beam(direction, origin=origin)
