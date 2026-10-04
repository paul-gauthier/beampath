"""Shared optical fixtures independent of the presentation examples."""
import pytest

from beampath import HWP, beamsplitter, detector, fiber_launch, mirror


@pytest.fixture
def fiber_mzi():
    """A fiber-fed interferometer for composition and row-connection checks."""
    setup = fiber_launch() >> beamsplitter("NPBS1", turn="left")
    lower = setup.straight() >> HWP() >> mirror(heading="north")
    upper = setup.reflect() >> mirror(heading="east") >> HWP()
    combined = lower.join(upper, beamsplitter("NPBS2", turn="right"))
    combined.reflect() >> detector()
    combined.straight() >> detector()
    return setup
