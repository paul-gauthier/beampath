# Development

[README](../README.md) · [Gallery](gallery.md) · [Components](components.md) · [API](api.md)

## Setup and checks

```sh
uv sync --extra dev --extra png --extra pdf
.venv/bin/python -m pytest
uv build
```

PNG/PDF checks and documentation generation need native Cairo as well as the
Python extras; see [export setup](api.md#export). Use the environment's interpreter
directly on macOS to preserve its library search path.

## Documentation

```sh
.venv/bin/python scripts/rebuild_docs.py
.venv/bin/python scripts/rebuild_docs.py --check
```

The gallery comes from example modules; the component catalog comes from factory
docstrings and demo functions. API summaries and style defaults come from Python.
The README hello block is generated from the same source as the gallery.

Edit sources, regenerate, inspect the Markdown and PNGs, and commit both. The
builder stages all previews before replacing outputs; failed rendering leaves
existing docs intact. Unchanged files are not rewritten. `--check` reports stale
or obsolete generated outputs without replacing them. Both commands work from
any directory when the script is invoked by its path. Preview comparisons ignore
floating-point metadata differences below SVG precision; pixels and attribution
text must still match.

Keep usage examples in the gallery, component-specific details in docstrings,
and essential cross-cutting conventions in the API page. Avoid duplicate guides
and exhaustive implementation narratives.

- [Adding examples](../examples/README.md)
- [Adding components and artwork](../src/beampath/components/README.md)

The optional `scripts/render_hello_social.py` helper builds the social image from
hello's source and setup. Run it separately when that artwork needs updating.
