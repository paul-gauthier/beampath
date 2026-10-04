import math
import xml.etree.ElementTree as ET

import pytest

from beampath import (
    ComponentError, ConnectionError, HWP, LayoutError, QWP, Setup, Style,
    beam, component, iris, spdc,
)
from beampath.render import tag


@pytest.mark.parametrize("factory", [spdc, lambda **kw: component("spdc", **kw)])
@pytest.mark.parametrize("incidence", [0, 90, 180, 270, 31.4])
@pytest.mark.parametrize("opening", [0, 20, 75.5, 180])
def test_spdc_outputs_follow_incidence(factory, incidence, opening):
    source = beam(incidence) >> factory(opening_angle=opening)
    origin = source.end.instance
    assert origin.spec.display_label == "SPDC"
    assert [p.name for p in origin.geometry.ports] == [
        "in", "pump", "signal", "idler", "signal_in", "idler_in",
    ]
    for name, turn in (("pump", 0), ("signal", -opening / 2), ("idler", opening / 2)):
        downstream = source.out(name) >> iris()
        assert downstream.end.instance.heading == pytest.approx((incidence + turn) % 360)
    assert {p.position for p in origin.geometry.ports} == {(0, 0)}


def test_spdc_default_angle_and_explicit_output_selection():
    for spec in (spdc(), component("spdc")):
        source = beam() >> spec
        before = source.setup.optics, source.setup.connections
        with pytest.raises(ConnectionError, match="select an output"):
            source >> iris()
        assert (source.setup.optics, source.setup.connections) == before
        assert (source.out("signal") >> iris()).end.instance.heading == 350
        assert (source.out("idler") >> iris()).end.instance.heading == 10
        assert (source.out("pump") >> iris()).end.instance.heading == 0


@pytest.mark.parametrize("angle", [-1, 180.1, float("inf"), float("nan"), None, "wide", [], {}])
def test_spdc_rejects_invalid_opening_angle(angle):
    for factory in (spdc, lambda **kw: component("spdc", **kw)):
        with pytest.raises(ComponentError):
            factory(opening_angle=angle)


def test_spdc_polarization_type_is_a_label_not_a_parameter():
    with pytest.raises(ComponentError, match="Unknown component parameter.*type"):
        component("spdc", type="II")


@pytest.mark.parametrize("mode", ["signal", "idler"])
@pytest.mark.parametrize("incidence", [0, 31.4, 90])
@pytest.mark.parametrize("opening", [0, 20, 180])
@pytest.mark.parametrize("pump_first", [False, True])
def test_optional_input_continues_along_output_in_either_connection_order(
    mode, incidence, opening, pump_first,
):
    setup = Setup()
    crystal = setup.add(spdc(opening_angle=opening))
    direction = (incidence + (-1 if mode == "signal" else 1) * opening / 2) % 360
    dx, dy = math.cos(math.radians(direction)), math.sin(math.radians(direction))
    incoming = setup.beam(direction, origin=(-300 * dx, -300 * dy)) >> iris()
    if pump_first:
        setup.beam(incidence).connect(crystal.input())
    incoming.connect(crystal.input(mode + "_in"))
    if not pump_first:
        setup.beam(incidence).connect(crystal.input())
    crystal.out(mode).append(iris(), distance=300)

    layout = setup.layout()
    assert crystal.instance.heading == pytest.approx(incidence)
    incoming, = [s for s in layout.segments if s.input == mode + "_in"]
    outgoing, = [s for s in layout.segments if s.source == crystal.id and s.output == mode]
    assert incoming.end == outgoing.start
    for segment in (incoming, outgoing):
        assert tuple((b - a) / segment.length for a, b in zip(segment.start, segment.end)) == (
            pytest.approx((dx, dy), abs=1e-8)
        )
    assert {s.input for s in layout.segments if s.target == crystal.id} == {"in", mode + "_in"}


@pytest.mark.parametrize("mode", ["signal", "idler"])
@pytest.mark.parametrize("failure", ["direction", "duplicate"])
def test_optional_input_rejects_invalid_connections_without_consuming_path(mode, failure):
    pump = beam() >> spdc()
    crystal = pump.end
    direction = -10 if mode == "signal" else 10
    if failure == "duplicate":
        existing = pump.setup.beam(direction) >> iris()
        existing.connect(crystal.input(mode + "_in"))
    incoming = pump.setup.beam(direction + (1 if failure == "direction" else 0)) >> iris()
    before = pump.setup.optics, pump.setup.connections
    message = "incoming direction disagrees" if failure == "direction" else "input is already connected"
    with pytest.raises(ConnectionError, match=message):
        incoming.connect(crystal.input(mode + "_in"))
    assert (pump.setup.optics, pump.setup.connections) == before
    incoming >> iris()  # Failed connections leave the cursor available.


@pytest.mark.parametrize("mode", ["signal", "idler"])
def test_optional_input_does_not_replace_required_pump(mode):
    setup = Setup()
    crystal = setup.add(spdc())
    setup.beam(-10 if mode == "signal" else 10).connect(crystal.input(mode + "_in"))
    with pytest.raises(LayoutError, match=r"\.in: required input is not connected"):
        setup.layout()


@pytest.mark.parametrize("incidence", [0, 90, 180, 270, 31.4])
def test_collinear_output_stubs_overlap_without_losing_port_identity(incidence):
    source = beam(incidence) >> spdc(opening_angle=0)
    layout = source.layout()
    outputs = [s for s in layout.segments if s.source == source.end.id]
    assert len(outputs) == 3
    assert {s.output for s in outputs} == {"pump", "signal", "idler"}
    assert len({s.start for s in outputs}) == len({s.end for s in outputs}) == 1
    placed = layout.placements[source.end.id]
    assert all(placed.port_direction(s.output) == pytest.approx(incidence) for s in outputs)
    root = ET.fromstring(source.to_svg())
    lines = root.find(f"{tag('g')}[@id='optical-path']").findall(tag("line"))
    assert {line.get("data-output") for line in lines if line.get("data-source")} == {
        "pump", "signal", "idler",
    }


@pytest.mark.parametrize("output", ["pump", "signal", "idler"])
@pytest.mark.parametrize("incidence", [0, 90, 31.4])
def test_collinear_common_path_draws_downstream_optics_once(output, incidence):
    source = beam(incidence) >> spdc(opening_angle=0)
    source.out(output).append(HWP(), distance=150) >> QWP()
    style = Style(open_length=200)
    layout = source.layout(style=style)
    outputs = [s for s in layout.segments if s.source == source.end.id]
    assert len(outputs) == 1
    assert outputs[0].output == output
    assert outputs[0].target is not None
    dx, dy = math.cos(math.radians(incidence)), math.sin(math.radians(incidence))
    for placed in layout.placements.values():
        x, y = placed.position
        assert x * dy - y * dx == pytest.approx(0, abs=1e-8)
    root = ET.fromstring(source.to_svg(style=style))
    assert [node.get("data-component") for node in root.find(f"{tag('g')}[@id='components']")] == [
        "spdc", "HWP", "QWP",
    ]


def test_noncollinear_unused_outputs_still_have_stubs():
    source = beam() >> spdc()
    source.out("signal") >> HWP()
    outputs = [s for s in source.layout().segments if s.source == source.end.id]
    assert {s.output for s in outputs} == {"pump", "signal", "idler"}
    assert {s.output for s in outputs if s.target is None} == {"pump", "idler"}


@pytest.mark.parametrize("label,expected", [(None, ["SPDC"]), ("", []), ("BBO, Type II", ["BBO, Type II"])])
def test_spdc_artwork_is_only_the_crystal_body_with_user_label(label, expected):
    source = beam() >> spdc(label)
    root = ET.fromstring(source.to_svg())
    assert [node.text for node in root.iter(tag("text"))] == expected
    artwork = root.find(f"{tag('g')}[@id='components']/{tag('g')}")
    assert [node.tag for node in artwork] == [tag("rect")]
    assert artwork[0].get("fill") == "#E0D0E8"
    asset = source.end.instance.spec.definition.artwork
    assert asset.source_url.endswith("/fs-spdc-type1.svg")
    assert "Creative Commons Attribution" in asset.attribution


def test_noncollinear_example_preserves_full_opening_angle_in_layout():
    from beampath.examples.spdc import build

    setup = build()
    layout = setup.layout()
    source = layout.placements[setup.end.id]
    assert source.port_direction("pump") == 0
    assert source.port_direction("signal") == 350
    assert source.port_direction("idler") == 10
    for name, turn in (("pump", 0), ("signal", -10), ("idler", 10)):
        segment, = [s for s in layout.segments if s.source == source.id and s.output == name]
        dx, dy = (segment.end[i] - segment.start[i] for i in (0, 1))
        assert math.degrees(math.atan2(dy, dx)) == pytest.approx(turn)
