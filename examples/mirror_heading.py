"""Set an absolute mirror heading, then make a relative 90-degree turn."""
# README:BEGIN
from beampath import beam, iris, mirror
# README:END
from beampath.examples import run_example


def build():
    """Turn an eastward beam north, then right toward an iris."""
    # README:BEGIN
    setup = beam("east") >> mirror(heading="north") >> mirror(turn="right") >> iris()
    # README:END
    return setup


if __name__ == "__main__":
    run_example(build, "mirror_heading")
