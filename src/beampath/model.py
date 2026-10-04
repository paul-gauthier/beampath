"""Physical optical graph and the mutable path-building DSL."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path as FilePath
from typing import TYPE_CHECKING

from .definitions import Chain, ComponentSpec, Geometry, Port
from .errors import ComponentError, ConnectionError
from .geometry import Point, aligned, finite, heading, point

if TYPE_CHECKING:
    from .layout import Layout, Style


@dataclass(frozen=True)
class OpticInstance:
    id: str
    spec: ComponentSpec
    heading: float | None = None
    at: Point | None = None
    geometry: Geometry = field(init=False, repr=False)

    def __post_init__(self):
        try:
            geometry = (self.spec.geometry if self.heading is None
                        else self.spec.geometry_for_heading(self.heading))
        except ComponentError as exc:
            raise ComponentError(f"{self.id} ({self.spec.display_label}): {exc}") from exc
        if self.heading is not None and any(p.absolute for p in geometry.ports):
            geometry = replace(geometry, ports=tuple(
                replace(p, direction=p.direction - self.heading, absolute=False) if p.absolute else p
                for p in geometry.ports))
        object.__setattr__(self, "geometry", geometry)

    def port(self, name: str, kind: str | None = None) -> Port:
        for port in self.geometry.ports:
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
    medium: str = "free_space"


@dataclass(frozen=True)
class Root:
    optic: str
    input: str | None
    direction: float
    origin: Point


@dataclass(frozen=True)
class _LayoutGroup:
    """A local coordinate frame, optionally arranging its children as rows."""

    entry: str
    origin: Point
    members: frozenset[str]
    children: tuple[_LayoutGroup, ...] = ()
    rows: bool = False
    gap: float | None = None

    def remap(self, mapping: dict[str, str], delta: Point) -> _LayoutGroup:
        return replace(self, entry=mapping[self.entry],
                       origin=(self.origin[0] + delta[0], self.origin[1] + delta[1]),
                       members=frozenset(mapping[ident] for ident in self.members),
                       children=tuple(child.remap(mapping, delta) for child in self.children))

    def extend(self, upstream: str, members: frozenset[str],
               children: tuple[_LayoutGroup, ...]) -> _LayoutGroup:
        if upstream not in self.members:
            return self
        if any(upstream in child.members for child in self.children):
            nested = tuple(child.extend(upstream, members, children) for child in self.children)
        else:
            nested = self.children + children
        return replace(self, members=self.members | members, children=nested)


@dataclass(frozen=True)
class InputRef:
    optic: OpticRef
    name: str


@dataclass(frozen=True)
class OpticRef:
    """A stable reference to a physical optic, used to select its inputs or outputs."""
    setup: Setup
    id: str

    @property
    def instance(self) -> OpticInstance:
        return self.setup._nodes[self.id]

    def input(self, name: str | None = None) -> InputRef:
        """Select a named input, or the component default when omitted, for path.connect()."""
        name = name if name is not None else self.instance.spec.definition.default_input
        if name is None:
            raise ConnectionError(f"{self.id}: this optic has no default input")
        self.instance.port(name, "input")
        return InputRef(self, name)

    def out(self, name: str) -> Path:
        """Select an unused output of this physical optic and return a path cursor."""
        self.instance.port(name, "output")
        if self.setup._output_used(self.id, name):
            raise ConnectionError(f"{self.id}.{name}: output is already connected")
        return Path(self.setup, self.id, name)

    def straight(self) -> Path:
        return self.out("straight")

    def turn(self) -> Path:
        return self.out("turn")

    def reflect(self) -> Path:
        return self.out("reflect")


class Setup:
    """Own a diagram containing paths, branches, and shared physical optics."""

    def __init__(self):
        self._nodes: dict[str, OpticInstance] = {}
        self._connections: list[Connection] = []
        self._roots: list[Root] = []
        # A copied fiber input loses its root but still starts the same oriented
        # free-space section. These seeds carry orientation, never placement.
        self._heading_seeds: dict[str, float] = {}
        self._layout_groups: tuple[_LayoutGroup, ...] = ()

    @property
    def optics(self) -> tuple[OpticInstance, ...]:
        return tuple(self._nodes.values())

    @property
    def connections(self) -> tuple[Connection, ...]:
        return tuple(self._connections)

    @contextmanager
    def _transaction(self):
        snapshot = (self._nodes.copy(), self._connections.copy(), self._roots.copy(),
                    self._heading_seeds.copy(), self._layout_groups)
        try:
            yield
        except Exception:
            (self._nodes, self._connections, self._roots, self._heading_seeds,
             self._layout_groups) = snapshot
            raise

    def _inherit_group(self, upstream: str | None, members: frozenset[str],
                       children: tuple[_LayoutGroup, ...] = ()):
        if upstream is not None and any(upstream in group.members for group in self._layout_groups):
            self._layout_groups = tuple(group.extend(upstream, members, children)
                                        for group in self._layout_groups)
        else:
            self._layout_groups += children

    def beam(self, direction: str | float = "east", *, origin: Point = (0, 0)) -> Path:
        """Start another path in this setup, with the given heading and first-optic origin."""
        return Path(self, initial_heading=heading(direction), origin=point(origin))

    def add(self, spec: ComponentSpec, *, at: Point | None = None) -> OpticRef:
        """Create a physical optic for explicit shared-input connections; return its reference."""
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
                 distance: float | None, *, resolve: bool = True, inherit: bool = True):
        outgoing = self._nodes[source].port(output, "output")
        incoming = self._nodes[target].port(input_name, "input")
        if outgoing.medium != incoming.medium:
            raise ConnectionError(f"{source}.{output} ({outgoing.medium}) cannot connect to "
                                  f"{target}.{input_name} ({incoming.medium})")
        if outgoing.medium == "fiber" and distance is not None:
            raise ConnectionError("distance= is only supported for free-space connections; "
                                  "use at= to position fiber components")
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
                                            source, output, target, input_name, distance, outgoing.medium))
        if inherit and not any(target in group.members for group in self._layout_groups):
            self._inherit_group(source, frozenset((target,)))
        if resolve:
            self._resolve_headings()

    def _bind_root(self, optic: str, input_name: str | None, direction: float, origin: Point,
                   *, resolve: bool = True):
        if input_name is not None and self._input_used(optic, input_name):
            raise ConnectionError(f"{optic}.{input_name}: input is already connected")
        if any(r.optic == optic and r.input == input_name for r in self._roots):
            raise ConnectionError(f"{optic}: port already starts a beam")
        self._roots.append(Root(optic, input_name, direction, origin))
        if resolve:
            self._resolve_headings()

    def _resolve_headings(self):
        # Propagate frame relations in both directions. A secondary input may be
        # connected first; it still refers to the same primary-relative frame.
        headings: dict[str, float] = {}
        todo: list[str] = []
        nodes = {ident: replace(node, heading=None) for ident, node in self._nodes.items()}

        def assign(ident: str, value: float, context: str):
            value %= 360
            if ident in headings:
                if not aligned(headings[ident], value):
                    raise ConnectionError(f"{context}: incoming direction disagrees with optic orientation")
            else:
                nodes[ident] = replace(nodes[ident], heading=value)
                headings[ident] = value
                todo.append(ident)

        for node in nodes.values():
            if node.geometry.heading is not None:
                assign(node.id, node.geometry.heading, node.id)
        for ident, direction in self._heading_seeds.items():
            if nodes[ident].geometry.heading is None:
                assign(ident, direction, ident)
        for root in self._roots:
            node = nodes[root.optic]
            if not any(p.medium == "free_space" for p in node.geometry.ports):
                continue
            port = node.port(root.input, "input") if root.input else None
            if port is not None and port.medium == "fiber":
                # Legacy beam(direction) >> fiber_launch() seeds the launch,
                # while an explicit launch heading overrides the shorthand default.
                if node.geometry.heading is None:
                    assign(root.optic, root.direction, root.optic)
            else:
                assign(root.optic, root.direction - (port.direction if port else 0), root.optic)
        adjacency: dict[str, list[Connection]] = {ident: [] for ident in self._nodes}
        for edge in self._connections:
            if edge.medium == "fiber":
                continue
            template = next(p for p in nodes[edge.source].spec.geometry.ports if p.name == edge.output)
            if template.absolute:
                incoming = nodes[edge.target].port(edge.input).direction
                assign(edge.target, template.direction - incoming, f"{edge.target}.{edge.input}")
                # An absolute output does not constrain the incoming heading.
                continue
            adjacency[edge.source].append(edge)
            adjacency[edge.target].append(edge)
        def propagate():
            while todo:
                ident = todo.pop(0)
                for edge in adjacency[ident]:
                    outgoing = nodes[edge.source].port(edge.output).direction
                    incoming = nodes[edge.target].port(edge.input).direction
                    if ident == edge.source:
                        assign(edge.target, headings[ident] + outgoing - incoming,
                               f"{edge.target}.{edge.input}")
                    else:
                        assign(edge.source, headings[ident] + incoming - outgoing,
                               f"{edge.source}.{edge.output}")
        propagate()
        for ident, node in nodes.items():
            if ident not in headings and node.geometry.default_heading is not None:
                assign(ident, node.geometry.default_heading, ident)
                propagate()
        self._nodes = nodes

    def layout(self, *, style: Style | None = None) -> Layout:
        """Solve positions and return an immutable snapshot of placements, beams, fibers, and labels."""
        from .layout import layout
        return layout(self, style=style)

    def to_svg(self, *, style: Style | None = None) -> str:
        """Return editable SVG text for the whole diagram without writing a file."""
        from .render import render_svg
        return render_svg(self.layout(style=style))

    def save(self, filename: str | FilePath, *, style: Style | None = None,
             width: int | None = None, dpi: float = 96) -> FilePath:
        """Save the whole diagram as SVG, PNG, or vector PDF, selected by the filename suffix.

        Return the output file path. PNG width is in pixels; PDF page width is
        width / dpi inches. SVG rejects width. PNG and PDF need their optional
        converter dependencies and native Cairo."""
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
    """A mutable cursor in a setup. Appending advances this same object; assignment does not copy it."""

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
        """Return a stable reference to the current physical optic, retained when this cursor advances."""
        if self._end is None:
            raise ConnectionError("This path has no first component yet")
        return OpticRef(self.setup, self._end)

    def _frontier(self) -> tuple[str, str]:
        self._check()
        if self._end is None:
            raise ConnectionError("This operation needs a component on the path")
        if self._port is None:
            outputs = [p for p in self.end.instance.geometry.ports if p.kind == "output"]
            if outputs:
                raise ConnectionError(f"{self._end}: select an output with out(), straight(), turn(), or reflect()")
            raise ConnectionError(f"{self._end}: this component ends the beam path")
        if self.setup._output_used(self._end, self._port):
            raise ConnectionError(f"{self._end}.{self._port}: output is already connected")
        return self._end, self._port

    def append(self, spec: ComponentSpec | Chain | Path, *, distance: float | None = None,
               at: Point | None = None) -> Path:
        """Append a component, chain, or independent copy of a built path; advance and return this cursor.

        distance fixes the new free-space gap between ports. at pins the
        component reference point. Both apply to the first optic of a chain.
        A copied path includes its entire setup, branches, and shared optics.
        It needs one connected root; the source remains unchanged. at moves
        the entry and its explicit pins together. See rows() for stacked stages."""
        self._check()
        if not isinstance(spec, (ComponentSpec, Chain, Path)):
            raise ConnectionError("append() needs a component specification, chain, or path")
        distance = _distance(distance)
        at = point(at) if at is not None else None
        old_cursor = self._end, self._port
        try:
            with self.setup._transaction():
                if isinstance(spec, Path):
                    self._append_path(spec, distance, at)
                else:
                    specs = spec.specs if isinstance(spec, Chain) else (spec,)
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

    def _append_path(self, source: Path, distance: float | None, at: Point | None,
                     *, inherit: bool = True):
        source._check()
        if source.setup is self.setup:
            raise ConnectionError("Cannot append a path from the same setup")
        if source._end is None:
            raise ConnectionError("The source path has no first component yet")
        if source._port is not None:
            source._frontier()  # Reject a stale selected output; terminals and groups are valid.
        if len(source.setup._roots) != 1:
            raise ConnectionError("Appending a path needs a source setup with exactly one root")
        root, = source.setup._roots
        outgoing: dict[str, list[str]] = {}
        for edge in source.setup._connections:
            outgoing.setdefault(edge.source, []).append(edge.target)
        reachable, todo = set(), [root.optic]
        while todo:
            ident = todo.pop()
            if ident not in reachable:
                reachable.add(ident)
                todo.extend(outgoing.get(ident, ()))
        if reachable != source.setup._nodes.keys():
            raise ConnectionError("Appending a path needs every source optic connected to its root")

        frontier = self._frontier() if self._end is not None else None
        if frontier is None and distance is not None:
            raise ConnectionError("The first component has no preceding segment to set a distance on")
        if frontier is not None and root.input is None:
            raise ConnectionError("Cannot append a stage whose entry optic has no input")
        origin = at if at is not None else (self._origin if frontier is None else None)
        delta = ((origin[0] - root.origin[0], origin[1] - root.origin[1])
                 if origin is not None else (0, 0))
        mapping = {}
        for node in source.setup.optics:
            pin = ((node.at[0] + delta[0], node.at[1] + delta[1])
                   if node.at is not None else None)
            if node.id == root.optic and at is not None:
                pin = at
            mapping[node.id] = self.setup.add(node.spec, at=pin).id
        self.setup._heading_seeds.update(
            (mapping[ident], direction) for ident, direction in source.setup._heading_seeds.items())
        entry = mapping[root.optic]
        if frontier is None:
            self.setup._bind_root(entry, root.input, self._initial_heading, origin, resolve=False)
        else:
            incoming = source.setup._nodes[root.optic].port(root.input, "input")
            if incoming.medium == "fiber" and any(
                p.medium == "free_space" for p in source.setup._nodes[root.optic].geometry.ports
            ):
                self.setup._heading_seeds[entry] = root.direction
            self.setup._connect(*frontier, entry, root.input, distance, resolve=False, inherit=False)
        # Clone edges in source order after the boundary, then resolve the whole
        # graph once: a partial branch or join can imply a different orientation.
        for edge in source.setup._connections:
            self.setup._connections.append(replace(
                edge, id=f"segment-{len(self.setup._connections) + 1:03d}",
                source=mapping[edge.source], target=mapping[edge.target]))
        self.setup._resolve_headings()
        self._end, self._port = mapping[source._end], source._port
        if inherit:
            groups = tuple(group.remap(mapping, delta) for group in source.setup._layout_groups)
            self.setup._inherit_group(frontier[0] if frontier else None,
                                      frozenset(mapping.values()), groups)
        return mapping

    def __rshift__(self, spec):
        return self.append(spec)

    def __irshift__(self, spec):
        return self.append(spec)

    def out(self, name: str) -> Path:
        """Select a named output using a new cursor; choose before continuing from a splitter."""
        self._check()
        return self.end.out(name)

    def straight(self) -> Path:
        return self.out("straight")

    def turn(self) -> Path:
        return self.out("turn")

    def reflect(self) -> Path:
        return self.out("reflect")

    def connect(self, target: InputRef, *, distance: float | None = None) -> OpticRef:
        """Connect to an existing optic input in the same setup; consume this cursor and return its optic reference."""
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
        """Join two paths in the same setup at a new two-input optic; consume both cursors and return its output cursor."""
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
    """Start a setup with an incoming stub at its first free-space input.

    origin locates the first optic, not the open end of the incoming beam.
    """
    return Setup().beam(direction, origin=origin)


def rows(*stages: Path, gap: float | None = None) -> Path:
    """Copy and fiber-connect stages in vertically stacked, entry-aligned rows.

    Each stage includes its entire setup. Sources remain unchanged; the result
    selects the last stage's endpoint. Pins are local to their stage, and later
    appends extend the row of their upstream optic. Row contents are measured
    at render time, with a minimum clear gap (default: the style's pitch).
    """
    if not stages or any(not isinstance(stage, Path) for stage in stages):
        raise ConnectionError("rows() needs one or more Path stages")
    if gap is not None:
        gap = finite(gap, "gap")
        if gap <= 0:
            raise ConnectionError("Row gap must be positive")
    # _append_path validates roots, reachability and cursor state. Read the
    # first root only to preserve its frame rather than supplying beam defaults.
    roots = stages[0].setup._roots
    result = beam(roots[0].direction, origin=roots[0].origin) if len(roots) == 1 else beam()
    children = []
    for index, stage in enumerate(stages):
        if index:
            ident, output = result._frontier()
            if result.setup._nodes[ident].port(output).medium != "fiber":
                raise ConnectionError("rows() requires fiber connections between stages")
        mapping = result._append_path(stage, None, None, inherit=False)
        root, = stage.setup._roots
        children.append(_LayoutGroup(
            mapping[root.optic], root.origin, frozenset(mapping.values()),
            tuple(group.remap(mapping, (0, 0)) for group in stage.setup._layout_groups)))
    result.setup._layout_groups = (_LayoutGroup(
        children[0].entry, children[0].origin, frozenset(result.setup._nodes),
        tuple(children), rows=True, gap=gap),)
    return result
