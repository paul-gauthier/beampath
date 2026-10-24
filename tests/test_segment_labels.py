"""Connection annotations survive graph building, composition, and rendering."""
from dataclasses import FrozenInstanceError
import json
import xml.etree.ElementTree as ET

import pytest

from beampath import (
    Artwork, ComponentDefinition, ComponentError, ComponentSpec, ConnectionError,
    Geometry, HWP, LayoutError, Port, SegmentLabel, Style, beam, beamsplitter, chain, detector,
    fiber_coupler, fiber_laser, fiber_launch, fiber_power_meter, fiber_splitter,
    inline_power_meter, label, mirror, rows,
)
from beampath.geometry import overlap
from beampath.layout import segment_intersects


SVG = "{http://www.w3.org/2000/svg}"


def segment_labels(layout):
    return [item for item in layout.labels if item.segment is not None]


def snapshot(path):
    return (path.setup.optics, path.setup.connections, tuple(path.setup._roots),
            dict(path.setup._output_labels), path.end, path._port, path._consumed)


def assert_clear(layout):
    lines = list(layout.segments) + [leg for route in layout.fibers for leg in route.legs]
    for index, item in enumerate(layout.labels):
        assert not any(overlap(item.bounds, optic.bounds) for optic in layout.placements.values())
        assert not any(overlap(item.bounds, other.bounds) for other in layout.labels[index + 1:])
        assert not any(segment_intersects(line.start, line.end, item.bounds) for line in lines)
        assert layout.bounds[0] <= item.bounds[0] <= item.bounds[2] <= layout.bounds[2]
        assert layout.bounds[1] <= item.bounds[1] <= item.bounds[3] <= layout.bounds[3]


def test_label_marker_is_reusable_immutable_and_joins_lines():
    marker = label("Pump", "405 nm\n2 mW")
    assert isinstance(marker, SegmentLabel)
    assert marker.text == "Pump\n405 nm\n2 mW"
    with pytest.raises(FrozenInstanceError):
        marker.text = "Changed"
    a = HWP("") >> marker >> HWP("")
    b = HWP("") >> marker >> HWP("")
    assert a.setup.connections[0].label == b.setup.connections[0].label == marker.text
    assert a.setup is not b.setup


@pytest.mark.parametrize("parts", [(), (None,), (123,), ("Pump", None), ("Pump", False)])
def test_label_rejects_missing_or_non_string_lines(parts):
    with pytest.raises((ComponentError, TypeError), match="[Ll]abel"):
        label(*parts)


@pytest.mark.parametrize("first,last,medium", [
    (HWP(""), HWP(""), "free_space"),
    (fiber_laser(""), inline_power_meter(""), "fiber"),
])
def test_marker_and_bare_string_create_the_same_labeled_connection(first, last, medium):
    explicit = first >> label("Signal", "810 nm") >> last
    shorthand = first >> "Signal\n810 nm" >> last
    assert len(explicit.setup.optics) == 2
    assert explicit.setup.connections == shorthand.setup.connections
    connection, = explicit.setup.connections
    assert connection.medium == medium
    assert connection.label == "Signal\n810 nm"
    layout = explicit.layout()
    drawn, = segment_labels(layout)
    assert drawn.optic is None
    assert (drawn.segment, drawn.text) == (connection.id, connection.label)
    assert shorthand.layout() == layout
    assert_clear(layout)


def test_label_applies_only_to_the_next_segment_and_preserves_optic_labels():
    path = HWP("First") >> label("Pump") >> HWP("Second") >> HWP("Third")
    assert [edge.label for edge in path.setup.connections] == ["Pump", None]
    assert [node.spec.display_label for node in path.setup.optics] == ["First", "Second", "Third"]
    assert [item.text for item in segment_labels(path.layout())] == ["Pump"]


def test_initial_and_open_beam_labels_move_to_their_connections():
    path = beam() >> label("Incident") >> HWP("") >> "Outgoing"
    layout = path.layout()
    incoming = next(item for item in layout.segments if item.source is None)
    outgoing = next(item for item in layout.segments if item.target is None)
    assert {item.segment: item.text for item in segment_labels(layout)} == {
        incoming.id: "Incident", outgoing.id: "Outgoing",
    }
    path >> HWP("")
    assert path.setup.connections[0].label == "Outgoing"
    assert {item.text for item in segment_labels(path.layout())} == {"Incident", "Outgoing"}


def test_invalid_initial_label_target_preserves_the_label_for_a_drawn_input():
    path = beam() >> label("Incident")
    with pytest.raises(ConnectionError, match="drawn input"):
        path >> fiber_laser("")
    assert not path.setup.optics
    path >> HWP("")
    assert path.setup._roots[0].label == "Incident"
    assert [item.text for item in segment_labels(path.layout())] == ["Incident"]


def test_open_fiber_label_is_retained_when_the_output_is_connected():
    path = fiber_laser("") >> label("PM fiber", "2 m")
    layout = path.layout()
    route, = layout.fibers
    drawn, = segment_labels(layout)
    assert (drawn.segment, drawn.text) == (route.id, "PM fiber\n2 m")
    assert route.target is None
    path >> fiber_power_meter("")
    assert path.setup.connections[0].label == drawn.text
    assert segment_labels(path.layout())[0].segment == path.setup.connections[0].id


@pytest.mark.parametrize("splitter,sink,select", [
    (beamsplitter("", turn="left"), detector(""), "reflect"),
    (fiber_splitter(""), fiber_power_meter(""), "turn"),
])
def test_branch_labels_require_output_selection_and_stay_on_that_output(splitter, sink, select):
    path = (fiber_laser("") if select == "turn" else HWP("")) >> splitter
    before = snapshot(path)
    with pytest.raises(ConnectionError, match="select an output"):
        path >> label("Ambiguous")
    assert snapshot(path) == before
    branch = getattr(path, select)() >> label("Monitor") >> sink
    connection = branch.setup.connections[-1]
    assert (connection.output, connection.label) == (select, "Monitor")
    assert branch.setup.connections[0].label is None
    assert [item.text for item in segment_labels(branch.layout())] == ["Monitor"]


def test_duplicate_label_rejects_atomically_and_the_original_is_used():
    path = HWP("") >> label("Original")
    before = snapshot(path)
    with pytest.raises(ConnectionError, match="[Ll]abel"):
        path >> "Replacement"
    assert snapshot(path) == before
    path >> HWP("")
    assert path.setup.connections[0].label == "Original"


def test_labels_reject_terminal_and_consumed_cursors():
    terminal = HWP("") >> detector("")
    before = snapshot(terminal)
    with pytest.raises(ConnectionError, match="ends the beam path"):
        terminal >> label("No segment")
    assert snapshot(terminal) == before
    path = beam() >> HWP("")
    path.connect(path.setup.add(detector("")).input())
    before = snapshot(path)
    with pytest.raises(ConnectionError, match="consumed"):
        path >> label("No segment")
    assert snapshot(path) == before


def test_failed_append_preserves_the_label_for_a_later_valid_connection():
    path = fiber_laser("") >> label("Survives failure")
    before = snapshot(path)
    with pytest.raises(ConnectionError, match="cannot connect"):
        path >> HWP("")
    assert snapshot(path) == before
    path >> inline_power_meter("")
    assert path.setup.connections[0].label == "Survives failure"
    assert_clear(path.layout())


def test_failed_chain_restores_consumed_boundary_and_internal_labels():
    path = fiber_laser("") >> label("Boundary")
    before = snapshot(path)
    with pytest.raises(ConnectionError, match="cannot connect"):
        path >> chain(inline_power_meter(""), label("Internal"), HWP(""))
    assert snapshot(path) == before
    path >> fiber_power_meter("")
    assert [edge.label for edge in path.setup.connections] == ["Boundary"]


def test_connect_to_existing_input_uses_the_selected_segment_label():
    path = HWP("") >> label("Shared input")
    target = path.setup.add(detector(""))
    assert path.connect(target.input()) == target
    connection, = path.setup.connections
    assert (connection.target, connection.label) == (target.id, "Shared input")
    assert segment_labels(path.layout())[0].segment == connection.id


def test_join_transfers_each_incoming_label_to_its_own_connection():
    split = fiber_launch("") >> beamsplitter("", turn="left")
    a = split.straight() >> HWP("") >> mirror(heading="north") >> label("Lower arm")
    b = split.reflect() >> mirror(heading="east") >> HWP("") >> "Upper arm"
    combined = a.join(b, beamsplitter("", turn="right"))
    edges = [edge for edge in combined.setup.connections if edge.target == combined.end.id]
    assert {edge.input: edge.label for edge in edges} == {
        "primary": "Lower arm", "secondary": "Upper arm",
    }


def test_failed_join_restores_both_incoming_labels_and_cursors():
    split = HWP("") >> beamsplitter("", turn="right")
    a, b = split.straight() >> label("Straight"), split.reflect() >> label("Reflected")
    before = snapshot(a), snapshot(b)
    with pytest.raises(ConnectionError, match="direction disagrees"):
        a.join(b, beamsplitter("", turn="left"))
    assert (snapshot(a), snapshot(b)) == before
    a >> detector("")
    b >> detector("")
    assert [edge.label for edge in split.setup.connections[-2:]] == ["Straight", "Reflected"]


def test_reusable_chain_preserves_labels_without_creating_extra_optics():
    unit = chain(HWP(""), label("First gap"), HWP(""), "Second gap", HWP(""))
    path = beam() >> unit
    assert len(path.setup.optics) == 3
    assert [edge.label for edge in path.setup.connections] == ["First gap", "Second gap"]
    assert_clear(path.layout())


def labeled_stage():
    return fiber_launch("") >> label("In stage") >> fiber_coupler("") >> label("Stage output")


def test_copy_remaps_internal_and_open_labels_without_mutating_the_source():
    source = labeled_stage()
    before = snapshot(source)
    destination = fiber_laser("") >> label("Stage input") >> source
    assert snapshot(source) == before
    assert [edge.label for edge in destination.setup.connections] == ["Stage input", "In stage"]
    assert {item.text for item in segment_labels(destination.layout())} == {
        "Stage input", "In stage", "Stage output",
    }
    destination >> fiber_power_meter("")
    assert destination.setup.connections[-1].label == "Stage output"
    assert snapshot(source) == before


def test_rows_preserve_labels_and_measure_them_without_mutating_stages():
    source = labeled_stage()
    before = snapshot(source)
    path = rows(source, source, gap=30)
    assert snapshot(source) == before
    assert [edge.label for edge in path.setup.connections] == ["In stage", "Stage output", "In stage"]
    layout = path.layout()
    labels = segment_labels(layout)
    assert sorted(item.text for item in labels) == ["In stage", "In stage", "Stage output", "Stage output"]
    assert len({item.segment for item in labels}) == 4
    assert layout == path.layout()
    assert_clear(layout)


@pytest.mark.parametrize("direction", [0, 90, 37])
def test_segment_labels_clear_artwork_other_labels_and_beams_deterministically(direction):
    path = (beam(direction) >> HWP("Input") >> label("Pump", "405 nm")
            >> HWP("Polarization") >> "Signal\n810 nm" >> HWP("Output"))
    before = snapshot(path)
    style = Style(pitch=80, font_size=28)
    layout = path.layout(style=style)
    assert len(segment_labels(layout)) == 2
    assert_clear(layout)
    assert path.layout(style=style) == layout
    assert snapshot(path) == before


def test_label_on_a_detoured_fiber_belongs_to_the_route_and_clears_every_leg():
    path = fiber_laser("") >> label("PM fiber", "2 m")
    path.append(inline_power_meter(""), at=(900, 0))
    obstacle = ComponentSpec(ComponentDefinition(
        "obstacle", "", Artwork((0, 0), (-40, -120, 40, 120),
                                 svg='<svg xmlns="http://www.w3.org/2000/svg"/>'),
        lambda _: Geometry((Port("in", "input", draw_lead_in=False),))))
    path.setup.beam(origin=(470, 0)) >> obstacle
    layout = path.layout()
    route = next(route for route in layout.fibers if route.target)
    assert len(route.points) > 2
    drawn, = segment_labels(layout)
    assert drawn.segment == route.id
    assert_clear(layout)


@pytest.mark.parametrize("first,last", [
    (HWP(""), HWP("")), (fiber_laser(""), inline_power_meter("")),
])
def test_long_labels_expand_automatic_gaps_without_changing_the_graph(first, last):
    style = Style(pitch=40)
    ordinary = first >> last
    path = first >> label("Transmission wavelength: 1550 nm") >> last
    before = snapshot(path)
    layout = path.layout(style=style)
    routes = layout.fibers if layout.fibers else layout.segments
    normal = ordinary.layout(style=style)
    normal_routes = normal.fibers if normal.fibers else normal.segments
    segment = next(item for item in routes if item.source and item.target)
    normal_segment = next(item for item in normal_routes if item.source and item.target)
    assert segment.length > normal_segment.length
    assert path.setup.connections[0].distance is None
    assert snapshot(path) == before
    assert_clear(layout)


def test_long_labels_preserve_an_explicit_distance_and_pin():
    path = beam(origin=(120, -80)) >> HWP("") >> label("Pump wavelength: 405 nm")
    path.append(HWP(""), distance=900, at=(1020, -80))
    before = snapshot(path)
    layout = path.layout(style=Style(pitch=40))
    connection = next(item for item in layout.segments if item.source and item.target)
    assert connection.length == pytest.approx(900)
    assert layout.placements[path.end.id].position == pytest.approx((1020, -80))
    assert snapshot(path) == before
    assert_clear(layout)


def test_impossible_fixed_label_reports_the_segment_without_relaxing_constraints():
    path = beam(origin=(120, -80)) >> HWP("") >> label("A very long wavelength annotation")
    path.append(HWP(""), distance=120, at=(240, -80))
    before = snapshot(path)
    with pytest.raises(LayoutError, match=r"segment-001.*A very long wavelength annotation.*no clear adjacent"):
        path.layout(style=Style(pitch=40))
    assert snapshot(path) == before


def test_a_label_on_a_hidden_output_reports_the_missing_segment_and_remains_usable():
    hidden = ComponentSpec(ComponentDefinition(
        "hidden-output", "", Artwork((0, 0), (-5, -5, 5, 5),
                                     svg='<svg xmlns="http://www.w3.org/2000/svg"/>'),
        lambda _: Geometry((Port("in", "input"), Port("out", "output", draw_open=False)))))
    path = beam() >> hidden >> label("Hidden output")
    before = snapshot(path)
    with pytest.raises(LayoutError, match=r"optic-001.out.*Hidden output.*no visible segment"):
        path.layout()
    assert snapshot(path) == before
    path >> HWP("")
    assert path.setup.connections[0].label == "Hidden output"
    assert [item.text for item in segment_labels(path.layout())] == ["Hidden output"]


@pytest.mark.parametrize("first,last", [
    (HWP(""), HWP("")), (fiber_laser(""), inline_power_meter("")),
])
def test_svg_and_manifest_preserve_multiline_segment_text_and_escape_xml(first, last):
    lines = ('Pump < 500 nm & "signal"', "Second > first")
    path = first >> label(*lines) >> last
    svg = path.to_svg()
    root = ET.fromstring(svg)
    item, = segment_labels(path.layout())
    text = root.find(f".//{SVG}text[@id='{item.segment}-label']")
    assert text is not None
    assert text.get("data-segment") == item.segment
    assert [span.text for span in text.findall(f"{SVG}tspan")] == list(lines)
    manifest = json.loads(root.find(f"{SVG}metadata/{SVG}metadata[@id='asset-attribution-manifest']").text)
    metadata, = [entry for entry in manifest["labels"] if entry.get("segment")]
    assert metadata["segment"] == item.segment
    assert metadata["text"] == "\n".join(lines)
    assert "&lt;" in svg and "&amp;" in svg


def test_empty_label_is_explicit_metadata_without_a_visible_text_block():
    path = HWP("") >> label("") >> HWP("")
    assert path.setup.connections[0].label == ""
    assert not segment_labels(path.layout())
