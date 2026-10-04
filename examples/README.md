# Adding examples

Each public `.py` file is automatically listed by the runner and
[gallery](../docs/gallery.md). Its basename is its slug; underscore-prefixed files
are helpers. Start with:

```python
"""A short description of what this setup demonstrates."""

from beampath import beam
from beampath.components import HWP

setup = beam() >> HWP()
```

Define `setup` at module level. Optionally define `style = Style(...)`. Helper
functions and intermediate paths are ordinary Python. Keep the docstring concise;
the gallery uses it as prose and displays the rest of the file as its code block.
There are no markers, metadata tables, or separate snippets to maintain.

Importing an example should only construct its diagram: no file writes, rendering,
argument parsing, or global component registration. For custom components, create
a `ComponentSpec(ComponentDefinition(...))` directly. Do not mutate setups imported
from other examples. Importing caches a mutable setup; use a fresh execution when
independent construction is needed.

```sh
python -m beampath.examples --diagram hello --png --pdf
python -m beampath.examples --diagram all --output-dir build/examples
```

SVG is always generated; `--png` and `--pdf` add formats. `--width` sets PNG width
(default 2400); PNGs use 600 dpi. PDFs use the canvas at 96 dpi. Directly executing
an example only constructs its setup. To export in your own code, call
`setup.save("diagram.svg", style=style)` (omit `style` if absent).

Run `.venv/bin/python scripts/rebuild_docs.py` to regenerate the gallery, README
hello block, and previews. Files under `images/` are generated; the separately
built `hello-social` artwork is retained. Run tests and commit source and outputs.
Generic checks discover new examples automatically; add specific tests when the
example depends on an important topology or geometry constraint.
