# beampath

A Python DSL for optical setup diagrams. Connect components with `>>`, let
beampath arrange them, and save editable SVG artwork, vector PDFs, or PNGs.

## Install

Python 3.11 or later:

```sh
pip install 'beampath @ git+https://github.com/paul-gauthier/beampath.git'
```

SVG export works with the base installation. For PNG/PDF, install the
[optional exporters and Cairo](docs/api.md#export).

## Hello, beampath

<!-- HELLO:BEGIN -->
![A laser beam folded by two mirrors, with a half-wave plate and fiber output.](examples/images/hello.png)

```python
from beampath.components import *

setup = (
    laser()
    >> mirror(turn="right")
    >> HWP()
    >> mirror(turn="left")
    >> fiber_coupler()
)

setup.save("hello.svg")
```
<!-- HELLO:END -->

Open `hello.svg` in a browser or vector editor; labels remain editable.
To render a bundled example:

```sh
python -m beampath.examples --diagram hello
```

## Documentation

- **[Example gallery](docs/gallery.md):** pictures and complete code for setups,
  branching, fiber connections, reusable stages, and custom components.
- **[Components](docs/components.md):** every builtin, with a minimal demo and API.
- **[API and conventions](docs/api.md):** construction, layout, styling, and export.
- **[Development](docs/development.md):** setup, checks, and documentation generation.

Connections must be acyclic; closed cavities and repeated passes through one
physical optic are unsupported.

## Artwork credits

Component artwork includes adaptations from the
[Photonics Component Library](https://github.com/itgall/photonics-component-library),
licensed under [CC BY 4.0](src/beampath/assets/LICENSE).
