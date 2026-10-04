# API and conventions

[README](../README.md) · [Gallery](gallery.md) · [Components](components.md)

Most diagrams can start from the [examples](gallery.md). Import core tools from
`beampath` and builtin factories from `beampath.components`.

## Essential conventions

- **Templates and instances:** a component specification or `chain()` is reusable;
  inserting it twice creates independent optics. Use `path.end` or `Setup.add()`
  to obtain a stable reference when multiple paths must share one physical optic.
- **Cursors:** `>>` and `.append()` advance the same mutable path. Assignment aliases
  it. `.out()` selects another cursor; `.straight()`, `.reflect()`, and `.turn()`
  are named-output shortcuts. Each port connects once. `connect()` and `join()`
  consume incoming cursors; select outputs on their returned reference/path.
- **Ownership:** connected or joined paths must belong to one setup. Separate
  `beam()` calls create separate setups; `Setup.beam()` adds roots to one diagram.
  Saving any path saves its entire setup. Appending a path copies its entire
  setup and leaves the source unchanged; `rows()` copies and fiber-connects stages.
- **Coordinates:** diagram units, with clockwise-positive degrees: east 0, south
  90, west 180, north 270. Compass names and numeric headings are accepted.
  Fiber has no optical heading; each launch starts a new free-space section.
- **Placement:** start with automatic layout. `distance=` fixes the free-space gap
  between ports; it cannot be used on a first component or a fiber connection.
  `at=(x, y)` pins a component reference point. The beam origin places its first
  optic. Pins and distances are required constraints; incompatible ones fail.
  Use `rows()` for explicit stage boundaries; it preserves local pins and headings.
- **Drawing:** crossings do not imply connections. Open ports have stubs, replaced
  when connected.
  Labels do not expand component spacing inside a stage; allow room when pinning.

## API summary

Signatures and descriptions below are generated from Python. The rendering
methods are shared by `Path` and `Setup` and are listed once under `Setup`.
For advanced details, consult the [model](../src/beampath/model.py),
[component definitions](../src/beampath/definitions.py), and
[layout types](../src/beampath/layout.py).

<!-- API:BEGIN -->
### Construction and connections

| API | Purpose |
|---|---|
| `beam(direction='east', *, origin=(0, 0))` | Start a setup with an incoming stub at its first free-space input. |
| `chain(*specs)` | Combine component specifications or existing chains into a reusable linear sequence. |
| `rows(*stages, gap=None)` | Copy and fiber-connect stages in vertically stacked, entry-aligned rows. |
| `Setup()` | Own a diagram containing paths, branches, and shared physical optics. |
| `Setup.beam(direction='east', *, origin=(0, 0))` | Start another path in this setup, with the given heading and first-optic origin. |
| `Setup.add(spec, *, at=None)` | Create a physical optic for explicit shared-input connections; return its reference. |
| `Path.append(spec, *, distance=None, at=None)` | Append a component, chain, or independent copy of a built path; advance and return this cursor. |
| `Path.out(name)` | Select a named output using a new cursor; choose before continuing from a splitter. |
| `Path.end` | Return a stable reference to the current physical optic, retained when this cursor advances. |
| `Path.connect(target, *, distance=None)` | Connect to an existing optic input in the same setup; consume this cursor and return its optic reference. |
| `Path.join(other, spec, *, at=None)` | Join two paths in the same setup at a new two-input optic; consume both cursors and return its output cursor. |
| `OpticRef.input(name=None)` | Select a named input, or the component default when omitted, for path.connect(). |
| `OpticRef.out(name)` | Select an unused output of this physical optic and return a path cursor. |

### Layout and export

| API | Purpose |
|---|---|
| `Setup.layout(*, style=None)` | Solve positions and return an immutable snapshot of placements, beams, fibers, and labels. |
| `Setup.to_svg(*, style=None)` | Return editable SVG text for the whole diagram without writing a file. |
| `Setup.save(filename, *, style=None, width=None, dpi=96)` | Save the whole diagram as SVG, PNG, or vector PDF, selected by the filename suffix. |

### Custom components

| API | Purpose |
|---|---|
| `ComponentSpec` | An immutable component template. Inserting it repeatedly creates independent physical optics. |
| `ComponentDefinition` | A geometry resolver, optionally refined once incidence is known. |
| `Artwork` | SVG artwork, optical anchor, conservative source bounds and credits. |
| `Geometry` | Local ports and artwork pose, relative to primary incidence. |
| `Port` | Heading of propagation, in the component's reference beam frame. |
| `component(name, label=None, **parameters)` | Create a specification from a registered component name, optional label, and component parameters. |
| `register_component(definition)` | Register a uniquely named component definition for use through component(). |

### Style

Control spacing, labels, beam appearance, and fiber routing.

pitch sets the minimum automatic port gap; clearance reserves artwork
space; margin surrounds the canvas; open_length sets nominal open stubs.
font_size, font_family, and label_gap control labels. beam_color and
beam_width control free space; fiber_color, fiber_width, and fiber_radius
control cables; background sets the canvas color. Dimensions are diagram
units. Numeric options must be positive, except fiber_radius may be zero.

| Field | Default |
|---|---|
| `pitch` | `190` |
| `clearance` | `20` |
| `margin` | `80` |
| `font_size` | `23` |
| `label_gap` | `14` |
| `open_length` | `95` |
| `beam_width` | `2.3` |
| `beam_color` | `'#CC0000'` |
| `font_family` | `'Helvetica, Arial, sans-serif'` |
| `background` | `'#FFFFFF'` |
| `fiber_color` | `'#1B1E89'` |
| `fiber_width` | `3.75` |
| `fiber_radius` | `10` |
<!-- API:END -->

## Export

`setup.save(filename, style=..., width=None, dpi=96)` selects the format by suffix
and returns the file path. All formats retain artwork attribution.

| Format | Dependencies | Sizing |
|---|---|---|
| SVG | Base package | Editable vectors/text; `width` is not accepted |
| PNG | `png` extra and native Cairo | `width` in pixels, aspect ratio preserved; `dpi` is resolution metadata |
| PDF | `pdf` extra and native Cairo | Vector output; page width is `width / dpi` inches |

Omitting `width` uses the canvas width. Width must be a positive integer and dpi
must be positive. PDF dpi controls page size, not vector quality.

```sh
pip install 'beampath[png,pdf] @ git+https://github.com/paul-gauthier/beampath.git'
```

On macOS with Homebrew, if the native Cairo library cannot be loaded:

```sh
brew install cairo
export DYLD_FALLBACK_LIBRARY_PATH="$(brew --prefix cairo)/lib${DYLD_FALLBACK_LIBRARY_PATH:+:$DYLD_FALLBACK_LIBRARY_PATH}"
.venv/bin/python -m beampath.examples --diagram hello --png
```

Use the environment's Python directly so macOS does not strip `DYLD_` variables
via an `/usr/bin/env` shebang. SVG needs no Cairo.

## Extending and inspecting

The [custom component example](gallery.md#custom_component) defines artwork and
ports directly. Reuse a `ComponentSpec`, or register its `ComponentDefinition`
under a unique name and construct specs with `component(name, ...)`.

Free-space port directions point into inputs and out of outputs. Positions use
the component's reference beam frame. Fiber ports use `medium="fiber"` and an
outward `exit_direction` drawing tangent. Artwork `center` and `bounds` use SVG
source units; `scale` converts them to diagram units. Include strokes in bounds
and preserve attribution. See [component authoring](../src/beampath/components/README.md).

`layout()` returns a snapshot: `placements` maps optic IDs to positions/bounds;
`segments`, `fibers`, and `labels` describe the drawing; `bounds` includes margins.
`setup.optics` and `setup.connections` expose immutable graph views.

## Errors and limits

`ComponentError` indicates an invalid component or parameter. `ConnectionError`
indicates an invalid port, heading, owner, consumed cursor, or cycle. `LayoutError`
indicates incompatible geometry, pins, or unresolved clearance/routing. All inherit
from `BeampathError` (`ValueError`). Export arguments may raise `ValueError`;
missing converters raise `RuntimeError`.

Connections must be acyclic. Closed cavities and repeated passes through one
physical optic are unsupported.
