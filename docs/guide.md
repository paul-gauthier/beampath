# User guide

[README](../README.md) · [Reference](reference.md) · [Development](development.md)

Contents: [Building a diagram](#building-a-diagram) ·
[Branching](#branching-and-shared-optics) · [Fiber](#fiber-connections) ·
[Reuse and positioning](#reuse-and-positioning) · [Export](#styling-and-export) ·
[Examples](#more-examples)

## Building a diagram

Start with the [hello example](../README.md#your-first-diagram), then build on
three ideas:

1. **Specifications** describe components. `HWP()` creates a reusable template;
   inserting it twice creates two independent optics.
2. **Paths** connect physical optics in a **Setup**. `>>` appends a component and
   advances the path. The setup owns the entire diagram, including branches.
3. **Layout and export** solve positions and render the setup. Saving any of its
   paths saves the whole diagram.

A shorthand chain such as `iris() >> HWP()` starts east. Use
`beam("north") >> iris()` to choose another direction; for one component, use
`beam() >> iris()`. Import `beam` from `beampath` and builtin components from
`beampath.components`.

Labels default to component names. Pass a label as the first argument, such as
`HWP("Pump HWP")`, or `label=""` to hide it. See the
[component table](reference.md#builtin-components) for available optics.

## Branching and shared optics

Use `beamsplitter(turn="left")` (the default) or `turn="right"` to choose the
side of its 90° reflected branch, relative to the primary incoming beam.
Select its `.straight()` or `.reflect()` output to start each arm.
Join the arms at one physical optic with `.join()`. This Mach–Zehnder
interferometer shares the recombining beamsplitter between both paths:

<!-- DOCS:BEGIN mzi -->
```python
from beampath.components import *

split = fiber_launch() >> beamsplitter("NPBS1", turn="right")
a = split.straight() >> HWP() >> mirror(heading="south")
b = split.reflect() >> LP() >> QWP() >> mirror(heading="east")
combined = a.join(b, beamsplitter("NPBS2", turn="left"))
combined.reflect() >> fiber_coupler()
combined.straight() >> iris()
split.save("mzi.svg")
```
<!-- DOCS:END mzi -->

![Mach–Zehnder interferometer with two arms and a shared recombining beamsplitter](../examples/images/mzi.png)

Runnable example: [mzi.py](../examples/mzi.py).

A path is a mutable cursor: assigning `alias = path` does not copy it. Selecting
an output gives you another cursor. After `a.join(b, spec)`, both incoming
cursors are consumed; select outputs on the returned cursor to continue.

For explicit control over shared inputs, use `Setup.add()` and
`path.connect()`, as in [shared_optic.py](../examples/shared_optic.py).
The [path reference](reference.md#paths-and-shared-optics) explains ownership,
port selection, and the distinction between templates and shared instances.

## Fiber connections

Fiber and free-space components use the same chaining API. `fiber_launch()`
converts fiber to free space; `fiber_coupler()` converts back. An inline power
meter lets the path continue, while `fiber_power_meter()` ends it.

<!-- DOCS:BEGIN mixed_fiber -->
```python
from beampath.components import *

setup = (
    fiber_laser("Tunable laser")
    >> inline_power_meter("Input power")
    >> fiber_launch()
    >> HWP()
    >> fiber_coupler()
    >> inline_power_meter("Output power")
)
setup.save("mixed_fiber.svg")
```
<!-- DOCS:END mixed_fiber -->

![A fiber laser and two power monitors connected through a free-space waveplate](../examples/images/mixed_fiber.png)

Runnable example: [mixed_fiber.py](../examples/mixed_fiber.py).

Connected ports must use the same medium. Fiber has no optical heading:
`fiber_launch(heading="north")` starts a new northward free-space section
regardless of the incoming cable's route.

Layout places fiber devices and routes their cables automatically. To guide a
route, pin a device with `at=(x, y)` as in
[fiber_bends.py](../examples/fiber_bends.py). Cable bends belong to the drawing;
they do not add components to the graph or represent physical cable lengths.
For a monitor branch, use a [fiber splitter](../examples/fiber_splitter.py)
and select its `.straight()` and `.turn()` outputs.

## Reuse and positioning

Use `chain()` to reuse a sequence of specifications. Let layout choose spacing
first, then use `distance=` for a particular free-space gap or `at=` to pin an
optic:

<!-- DOCS:BEGIN reuse -->
```python
from beampath import beam, chain
from beampath.components import *

polarization = chain(LP(), HWP(), QWP())
path = beam() >> polarization >> polarization  # Six independent optics.
path.append(iris(), distance=250)
path.append(mirror(turn="right"), at=(2000, 0))
path.save("reuse.svg")
```
<!-- DOCS:END reuse -->

![Two copies of a polarization chain followed by an iris and a positioned mirror](../examples/images/reuse.png)

Runnable example: [reuse.py](../examples/reuse.py).

`distance` measures between the connected ports; `at` fixes a component's
reference point. These are required constraints, so incompatible choices raise
`LayoutError`. Fiber connections accept positions but not `distance`.
See [spacing rules](reference.md#spacing-and-positioning) for origins, clearance,
and how constraints apply to a chain.

## Styling and export

Pass a `Style` to layout or export to change spacing, labels, and appearance.
`layout()` returns a snapshot for inspection, `to_svg()` returns SVG text, and
`save()` writes a file:

<!-- DOCS:BEGIN rendering -->
```python
from beampath import Style, beam
from beampath.components import *

STYLE = Style(pitch=220, font_size=20, beam_color="#1f77b4")

path = beam() >> LP() >> HWP() >> QWP()

layout = path.layout(style=STYLE)
svg_text = path.to_svg(style=STYLE)
path.save("rendering.png", style=STYLE, width=2400, dpi=600)
```
<!-- DOCS:END rendering -->

![A linear polarizer and two waveplates with custom spacing and a blue beam](../examples/images/rendering.png)

Runnable example: [rendering.py](../examples/rendering.py).

The PNG call above requires the optional converter and native Cairo. For SVG,
use `path.save("rendering.svg", style=STYLE)` without `width`; for PDF, use
`path.save("rendering.pdf", style=STYLE)`. The
[rendering reference](reference.md#rendering) covers dependencies, dimensions,
PDF page size, and troubleshooting.

## More examples

Each file is runnable from a checkout; the installed package also includes the
examples. To run one without downloading its source:

```sh
python -m beampath.examples --diagram mzi
```

This writes SVG under `build/examples/`. Add `--png` or `--pdf` after installing
the corresponding [export dependencies](reference.md#rendering).
See [example commands](development.md#running-examples) for all CLI options.

| Example | Demonstrates | Preview |
|---|---|---|
| [hello.py](../examples/hello.py) | A first diagram | [Image](../examples/images/hello.png) |
| [cage.py](../examples/cage.py) | A longer linear chain | [Image](../examples/images/cage.png) |
| [mirror_heading.py](../examples/mirror_heading.py) | Absolute headings and relative turns | [Image](../examples/images/mirror_heading.png) |
| [mzi.py](../examples/mzi.py) | Branching and recombination | [Image](../examples/images/mzi.png) |
| [shared_optic.py](../examples/shared_optic.py) | Explicit shared inputs | [Image](../examples/images/shared_optic.png) |
| [mixed_fiber.py](../examples/mixed_fiber.py) | Fiber/free-space transitions | [Image](../examples/images/mixed_fiber.png) |
| [fiber_bends.py](../examples/fiber_bends.py) | A pinned fiber device | [Image](../examples/images/fiber_bends.png) |
| [fiber_splitter.py](../examples/fiber_splitter.py) | A fiber monitor branch | [Image](../examples/images/fiber_splitter.png) |
| [reuse.py](../examples/reuse.py) | Reusable chains and spacing constraints | [Image](../examples/images/reuse.png) |
| [rendering.py](../examples/rendering.py) | Styling and export | [Image](../examples/images/rendering.png) |
| [custom_component.py](../examples/custom_component.py) | Custom artwork and named ports | [Image](../examples/images/custom_component.png) |
