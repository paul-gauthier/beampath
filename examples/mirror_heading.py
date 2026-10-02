"""Set an absolute mirror heading, then make a relative 90-degree turn."""
from beampath import beam, iris, mirror
from beampath.examples import run_example


def build():
    """Turn an eastward beam north, then right toward an iris."""
    setup = beam("east") >> mirror(heading="north") >> mirror(turn="right") >> iris()
    return setup


if __name__ == "__main__":
    run_example(build, "mirror_heading")
