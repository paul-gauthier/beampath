# beampath

A Python DSL for optical setup diagrams. Connect components with `>>`, let
beampath arrange them, and save editable SVG artwork, vector PDFs, or PNGs.

## Install

Python 3.11 or later is required. Install from GitHub:

```sh
pip install 'beampath @ git+https://github.com/paul-gauthier/beampath.git'
```

SVG export works with the base installation. For PNG or PDF, see
[export dependencies and Cairo setup](docs/reference.md#rendering).

## Hello, beampath

Start with a fiber launch, two mirrors, a half-wave plate, and a fiber coupler.
`>>` connects them in beam order:

<!-- DOCS:BEGIN hello -->
```python
from beampath.components import *

setup = (
    fiber_launch()
    >> mirror(turn="right")
    >> HWP()
    >> mirror(turn="left")
    >> fiber_coupler()
)
setup.save("hello.svg")
```
<!-- DOCS:END hello -->

![A fiber launch and fiber coupler connected through two mirrors and a half-wave plate](examples/images/hello.png)

Runnable example: [hello.py](examples/hello.py).

Save the code as `hello.py` and run it with Python to create `hello.svg`.
Open the SVG in a browser or vector editor. Component labels remain editable.

## What you can build

- Free-space chains with mirrors, polarizers, waveplates, filters, and apertures.
- Branching paths and interferometers with shared physical optics.
- Fiber paths with lasers, splitters, power meters, and free-space transitions.
- Reusable chains and custom components with your own SVG artwork and ports.

Layout preserves beam headings and solves spacing, with optional position and
distance constraints. Fiber connections route around components and labels.
Styles control labels, colors, spacing, and cable appearance.

beampath draws schematic diagrams; it does not simulate optical power or
polarization. Connections must be acyclic: closed cavities and repeated passes
through the same optic are unsupported. Incompatible geometry or unresolved
overlaps produce an error identifying a nearby component or port.

## Documentation

- [User guide](docs/guide.md)
- [Practical reference](docs/reference.md)
- [Example index](docs/guide.md#more-examples)
- [Rendering reference](docs/reference.md#rendering)
- [Development notes](docs/development.md)

## Artwork credits

Component artwork includes adaptations from the
[Photonics Component Library](https://github.com/itgall/photonics-component-library),
licensed under [CC BY 4.0](src/beampath/assets/LICENSE).
