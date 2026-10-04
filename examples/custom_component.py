"""Define inline artwork and three named output ports for a custom component."""

from beampath import (
    Artwork, ComponentDefinition, ComponentSpec, Geometry, Port, beam,
)
from beampath.components import *


def fork_geometry(parameters):
    return Geometry((
        Port("in", "input", 0, (-10, 0)),
        Port("forward", "output", 0, (10, 0)),
        Port("up", "output", 270, (0, -10)),
        Port("down", "output", 90, (0, 10)),
    ))


fork_spec = ComponentSpec(ComponentDefinition(
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

setup = beam() >> fork_spec
setup.out("forward") >> LP()
setup.out("up") >> HWP()
setup.out("down") >> QWP()
