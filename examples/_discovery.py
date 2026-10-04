"""Discover diagram modules without importing or rendering them."""
from pathlib import Path


def example_names(directory=None):
    """Return public Python file stems, with hello first, then alphabetical."""
    directory = Path(directory) if directory is not None else Path(__file__).parent
    return tuple(sorted(
        (path.stem for path in directory.glob("*.py") if not path.name.startswith("_")),
        key=lambda name: (name != "hello", name),
    ))
