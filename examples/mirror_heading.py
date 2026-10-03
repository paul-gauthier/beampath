"""Set an absolute mirror heading, then make a relative 90-degree turn."""
# DOCS:BEGIN
from beampath import beam
from beampath.components import *
# DOCS:END
from beampath.examples import run_example


def build():
    """Turn an eastward beam north, then right toward an iris."""
    # DOCS:BEGIN
    setup = beam("east") >> mirror(heading="north") >> mirror(turn="right") >> iris()
    # DOCS:END
    return setup


if __name__ == "__main__":
    run_example(build, "mirror_heading")
