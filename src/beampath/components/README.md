# Adding builtin components

Use one module per component, named after its factory (lowercase filenames).
Keep its `ComponentDefinition`, geometry resolver, factory, and `demo()` together.
Reuse private helpers in `_shared.py` where appropriate. Export the factory through
this package's `__init__.py` and `__all__`; top-level `beampath` exports follow it.
The component catalog discovers these exports automatically.

The factory docstring is the component's API documentation: explain what it draws,
its ports, and any meaningful options or restrictions. Defaults come from its real
signature. Common label conventions are documented once in the catalog.

Provide a parameterless demo with its own public imports and a final `return setup`:

```python
def demo():
    """Show the component with its open beam ports."""
    from beampath import beam
    from beampath.components import HWP

    setup = beam() >> HWP()
    return setup
```

The catalog shows this body without the docstring or return and renders its setup.
A single component and its open beam/fiber stubs usually suffice. Keep demos short,
self-contained, and free of file writes. No extraction markers are needed.

## Artwork and geometry

**Check the [Photonics Component Library](https://github.com/itgall/photonics-component-library)
for suitable existing assets before creating bespoke SVGs.** Bundled artwork,
[license](../assets/LICENSE), and [provenance](../assets/provenance.json) live in
`src/beampath/assets/`. Preserve source URLs, licenses, adaptation notes, and hashes.

Use artwork bounds including strokes and intrinsic text. Place port anchors at
beam/cable attachments; free-space directions follow propagation, while fiber
exit directions are outward drawing tangents. Geometry resolvers must be pure.
Keep labels and demonstration beams out of artwork where the renderer supplies them.

Run `.venv/bin/python scripts/rebuild_docs.py`, inspect the preview in the
[catalog](../../../docs/components.md), and run the tests. Add geometry/port tests
for new behavior; the catalog checks require every exported factory to have a
usable docstring and demo. Commit source, asset provenance, and generated outputs.
