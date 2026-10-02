"""Errors reported at the component, connection, or placement involved."""


class BeampathError(ValueError):
    """Base class for invalid optical diagrams."""


class ComponentError(BeampathError):
    """An invalid component definition or specification."""


class ConnectionError(BeampathError):
    """An invalid graph connection or path operation."""


class LayoutError(BeampathError):
    """The supplied graph and geometry cannot be placed readably."""
