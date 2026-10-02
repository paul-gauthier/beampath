"""Compose optical setup diagrams with >> and named beam paths."""
from .definitions import (
    Artwork, Chain, ComponentDefinition, ComponentSpec, Geometry, Port,
    chain, component, register_component,
)
from .components import HWP, LP, QWP, beamsplitter, fiber_launch, iris, mirror
from .errors import BeampathError, ComponentError, ConnectionError, LayoutError
from .model import InputRef, OpticRef, Path, Setup, beam
from .layout import Label, Layout, PlacedOptic, Segment, Style

__all__ = [
    "beam", "fiber_launch", "mirror", "beamsplitter", "iris", "LP", "HWP", "QWP",
    "chain", "component", "register_component", "Setup", "Path", "OpticRef", "InputRef",
    "Artwork", "Port", "Geometry", "ComponentDefinition", "ComponentSpec", "Chain",
    "BeampathError", "ComponentError", "ConnectionError", "LayoutError",
    "Style", "Layout", "PlacedOptic", "Segment", "Label",
]
