"""Define inline artwork and three named output ports for a custom component."""
# DOCS:BEGIN
from beampath import (
    Artwork, ComponentDefinition, Geometry, Port,
    beam, component, register_component,
)
from beampath.components import *
# DOCS:END
from beampath.examples import run_example


# DOCS:BEGIN
def fork_geometry(parameters):
    return Geometry((
        Port("in", "input", 0, (-10, 0)),
        Port("forward", "output", 0, (10, 0)),
        Port("up", "output", 270, (0, -10)),
        Port("down", "output", 90, (0, 10)),
    ))


register_component(ComponentDefinition(
    name="fork",
    default_label="Fork",
    artwork=Artwork(
        center=(0, 0), bounds=(-10, -10, 10, 10),
        svg='<svg xmlns="http://www.w3.org/2000/svg">'
            '<rect x="-10" y="-10" width="20" height="20" fill="#d5d8e8"/>'
            '</svg>',
        attribution="beampath custom component example artwork",
    ),
    resolve=fork_geometry,
))
# DOCS:END


def build():
    """Connect different optics to a custom component's three outputs."""
    # DOCS:BEGIN
    fork = beam() >> component("fork")
    fork.out("forward") >> LP()
    fork.out("up") >> HWP()
    fork.out("down") >> QWP()
    # DOCS:END
    return fork


if __name__ == "__main__":
    run_example(build, "custom_component")
