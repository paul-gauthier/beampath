"""Compose optical setup diagrams with >> and named beam paths."""
from .definitions import (
    Artwork, Chain, ComponentDefinition, ComponentSpec, Geometry, Port, SegmentLabel,
    chain, component, label, register_component,
)
from .components import *
from .components import __all__ as _component_names
from .errors import BeampathError, ComponentError, ConnectionError, LayoutError
from .model import InputRef, OpticRef, Path, Setup, beam, rows
from .layout import FiberRoute, Label, Layout, PlacedOptic, Segment, Style

__all__ = _component_names + [
    "beam", "rows", "label", "SegmentLabel",
    "chain", "component", "register_component", "Setup", "Path", "OpticRef", "InputRef",
    "Artwork", "Port", "Geometry", "ComponentDefinition", "ComponentSpec", "Chain",
    "BeampathError", "ComponentError", "ConnectionError", "LayoutError",
    "Style", "Layout", "PlacedOptic", "Segment", "FiberRoute", "Label",
]
