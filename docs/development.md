# Development

[README](../README.md) · [User guide](guide.md) · [Reference](reference.md)

## Setup and checks

From a checkout, using Python 3.11 or later:

```sh
uv sync --extra dev --extra png --extra pdf
.venv/bin/python -m pytest
uv build
```

PNG/PDF checks need native Cairo as well as the Python extras. Follow the
[Cairo setup](reference.md#cairo-troubleshooting) before running them; without
the converters, the corresponding tests skip. Use the environment's interpreter
directly to preserve the macOS library search path.

Tests cover graph operations, layout, example scripts, bundled artwork hashes,
attribution, PNG pixels, vector PDFs, documentation snippets, and rendering from
an installed wheel.

## Running examples

```sh
.venv/bin/python examples/hello.py --png --pdf
.venv/bin/python -m beampath.examples --diagram all --png --pdf
```

The module command works after installing the package, too. Use `--diagram`
with a name from the [example index](guide.md#more-examples), or `all` to render
every example. Without it, the module renders `cage`.

| Option | Effect |
|---|---|
| `--output-dir PATH` | Output directory; defaults to `build/examples/` |
| `--png` | Add PNG to SVG export |
| `--pdf` | Add PDF to SVG export |
| `--width PIXELS` | PNG width; defaults to 2400 |

CLI PNGs include 600 dpi metadata. CLI PDFs use the canvas size at 96 dpi;
`--width` does not change their page size. For custom PDF sizing, use
[`save()`](reference.md#rendering) directly.

## Updating documentation

```sh
.venv/bin/python scripts/rebuild_docs.py
```

The helper refreshes marked snippets across the README and documentation pages,
then all example PNGs in `examples/images/`. It works from any directory when
invoked by its path. It validates selected snippets before rendering and reads
all rendered previews before replacing tracked outputs. Invalid snippets or
failed/incomplete rendering leave the documentation and existing previews intact.
Unchanged files are not rewritten.

Edit runnable code in `examples/`, not its generated Markdown copy. Regions
between `# DOCS:BEGIN` and `# DOCS:END` are joined and dedented, excluding function
wrappers and CLI plumbing. The matching Markdown block uses
`<!-- DOCS:BEGIN name -->` and `<!-- DOCS:END name -->`. The helper's `SAVE_CALLS`
adds standalone export statements. Edit prose outside those blocks directly.

When adding an example, register it in the example CLI, add relevant example
test coverage, and add a source/preview link to the guide's index. All registered
examples receive previews. Embed a snippet only when it teaches a distinct
workflow; then add its export statement to `SAVE_CALLS` and place a marked block
on the appropriate page. An example does not need an embedded snippet.

Keep documentation organized by reader task:

- **README:** installation, one first diagram, capabilities, and navigation.
- **Guide:** workflows and selected walkthroughs.
- **Reference:** options, behavior contracts, export troubleshooting, and extensions.
- **Development:** setup, checks, and maintenance commands.

Give each explanation one primary home and link to it elsewhere. New features
do not automatically add README sections. Keep implementation details in source
docstrings and regression tests; describe current behavior instead of development
history. Add a new documentation page to the helper's `DOCUMENTS` list if needed.

The separate `scripts/render_hello_social.py` helper reads the marked hello
snippet from the README and produces the existing social artwork. Run it only
when that artwork needs refreshing.

## Artwork and provenance

Bundled SVG assets, their [license](../src/beampath/assets/LICENSE), and
[source provenance](../src/beampath/assets/provenance.json) live in
`src/beampath/assets/` and ship with the package. Builtin definitions select and
transform artwork in `src/beampath/components.py`.

Preserve credits and source hashes when changing assets. PCL adaptations retain
CC BY 4.0 attribution; the noise eater and fiber splitter use original beampath
schematics. Export tests check that attribution survives SVG, PNG, and PDF output.
