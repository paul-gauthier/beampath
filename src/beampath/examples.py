"""Reference setups that exercise composition and shared optics."""
from .components import HWP, LP, QWP, beamsplitter, fiber_launch, iris, mirror


def cage_system():
    return (
        fiber_launch("KT120", role="launch")
        >> mirror("Corner mirror", angle=-45)
        >> mirror("Corner mirror", angle=45)
        >> iris()
        >> LP("CRM1PT")
        >> HWP("K10CR1")
        >> QWP("DDR25")
        >> HWP("DDR25")
        >> LP("CRM1PT")
        >> iris()
        >> mirror("Corner mirror", angle=45)
        >> mirror("Corner mirror", angle=-45)
        >> fiber_launch("KT120", role="couple")
    )


def mzi():
    split = fiber_launch("KT120", role="launch") >> beamsplitter("BS1", angle=-45)
    a = split.straight() >> HWP() >> mirror(angle=-45)
    b = split.reflect() >> LP() >> QWP() >> mirror(angle=45)
    combined = a.join(b, beamsplitter("BS2", angle=45))
    combined.reflect() >> fiber_launch("KT120", role="couple")
    combined.straight() >> iris()
    return split
