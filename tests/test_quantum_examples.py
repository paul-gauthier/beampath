"""Physical topology and analytical conventions of the quantum-optics gallery."""
from itertools import product
import math
import runpy

import pytest


def diagram(name):
    namespace = runpy.run_module("beampath.examples." + name)
    setup = namespace["setup"].setup
    nodes = {node.id: node for node in setup.optics}
    edges = {(edge.source, edge.output): edge for edge in setup.connections}
    return namespace, nodes, edges


def kind(node):
    return node.spec.definition.name


def route(nodes, edges, source, port):
    """Follow a named mode through single-path optics to its next branch or sink."""
    visited = []
    while True:
        edge = edges[source.id, port]
        source = nodes[edge.target]
        visited.append(source)
        if kind(source) not in {"mirror", "HWP", "bandpass_filter"}:
            return source, visited, edge
        port = "out"


def detector_outputs(nodes, edges, splitter):
    outputs = {}
    for port in ("straight", "reflect"):
        sink, optics, _ = route(nodes, edges, splitter, port)
        assert kind(sink) == "detector"
        assert len(optics) == 1
        assert not any(source == sink.id for source, _ in edges)
        outputs[port] = sink.spec.display_label
    return outputs


def test_hom_interferes_both_photons_at_one_physical_beamsplitter():
    _, nodes, edges = diagram("hom")
    crystal, = [node for node in nodes.values() if kind(node) == "spdc"]
    signal, signal_optics, signal_edge = route(nodes, edges, crystal, "signal")
    idler, idler_optics, idler_edge = route(nodes, edges, crystal, "idler")
    assert signal.id == idler.id
    assert kind(signal) == "beamsplitter"
    assert {signal_edge.input, idler_edge.input} == {"primary", "secondary"}
    assert [kind(node) for node in signal_optics] == ["bandpass_filter", "mirror", "beamsplitter"]
    assert [kind(node) for node in idler_optics] == ["bandpass_filter", "mirror", "beamsplitter"]
    assert signal_optics[0].spec.display_label == idler_optics[0].spec.display_label
    assert idler_optics[1].spec.display_label == "Delay τ"
    assert detector_outputs(nodes, edges, signal) == {"straight": "D1", "reflect": "D2"}
    assert kind(route(nodes, edges, crystal, "pump")[0]) == "beam_block"


def test_hbt_herald_is_separate_from_the_split_signal():
    _, nodes, edges = diagram("hbt")
    crystal, = [node for node in nodes.values() if kind(node) == "spdc"]
    herald, herald_optics, _ = route(nodes, edges, crystal, "idler")
    assert kind(herald) == "detector" and herald.spec.display_label == "Herald"
    assert len(herald_optics) == 1
    splitter, optics, _ = route(nodes, edges, crystal, "signal")
    assert [kind(node) for node in optics] == ["bandpass_filter", "mirror", "beamsplitter"]
    assert detector_outputs(nodes, edges, splitter) == {"straight": "D1", "reflect": "D2"}
    assert len([node for node in nodes.values() if kind(node) == "detector"]) == 3
    assert kind(route(nodes, edges, crystal, "pump")[0]) == "beam_block"


def analyzer(nodes, edges, crystal, port, name):
    splitter, optics, edge = route(nodes, edges, crystal, port)
    assert [kind(node) for node in optics] == ["mirror", "HWP", "PBS"]
    assert edge.input == "primary"
    assert detector_outputs(nodes, edges, splitter) == {
        "straight": name + " +", "reflect": name + " −",
    }
    assert not any(e.target == splitter.id and e.input == "secondary" for e in edges.values())
    return splitter, optics[1]


def test_chsh_has_independent_analyzers_and_correct_waveplate_settings():
    namespace, nodes, edges = diagram("chsh")
    crystal, = [node for node in nodes.values() if kind(node) == "spdc"]
    assert "Ψ−" in crystal.spec.display_label
    alice, a_hwp = analyzer(nodes, edges, crystal, "signal", "Alice")
    bob, b_hwp = analyzer(nodes, edges, crystal, "idler", "Bob")
    assert alice.id != bob.id and a_hwp.id != b_hwp.id
    assert kind(route(nodes, edges, crystal, "pump")[0]) == "beam_block"
    assert namespace["alice_angles"] == (0, 45)
    assert namespace["bob_angles"] == (22.5, -22.5)

    # Recover the actual HWP labels: a HWP at phi followed by H/V analysis
    # measures at 2*phi. Check these displayed settings, not just constants.
    def measurement_angles(waveplate):
        settings = waveplate.spec.display_label.splitlines()[1].split(" / ")
        return tuple(2 * float(angle.removesuffix("°")) for angle in settings)

    a, ap = measurement_angles(a_hwp)
    b, bp = measurement_angles(b_hwp)
    assert (a, ap) == namespace["alice_angles"]
    assert (b, bp) == namespace["bob_angles"]

    def singlet_correlation(alpha, beta):
        return -math.cos(math.radians(2 * (alpha - beta)))

    s = (singlet_correlation(a, b) + singlet_correlation(a, bp)
         + singlet_correlation(ap, b) - singlet_correlation(ap, bp))
    assert abs(s) == pytest.approx(2 * math.sqrt(2))


def test_swapping_combines_inner_photons_and_preserves_outer_analyzers():
    _, nodes, edges = diagram("swapping")
    c1, c2 = [node for node in nodes.values() if kind(node) == "spdc"]
    assert all("Ψ−" in node.spec.display_label for node in (c1, c2))
    bell1, inner1, edge1 = route(nodes, edges, c1, "idler")
    bell2, inner2, edge2 = route(nodes, edges, c2, "signal")
    assert bell1.id == bell2.id and kind(bell1) == "beamsplitter"
    assert {edge1.input, edge2.input} == {"primary", "secondary"}
    for path in (inner1, inner2):
        assert [kind(node) for node in path] == ["bandpass_filter", "mirror", "beamsplitter"]
    assert inner1[0].spec.display_label == inner2[0].spec.display_label
    assert inner2[1].spec.display_label == "Delay τ"
    assert detector_outputs(nodes, edges, bell1) == {"straight": "B1", "reflect": "B2"}
    alice, _ = analyzer(nodes, edges, c1, "signal", "Alice")
    bob, _ = analyzer(nodes, edges, c2, "idler", "Bob")
    assert alice.id != bob.id
    assert len([node for node in nodes.values() if kind(node) == "detector"]) == 6

    incoming = {(edge.target, edge.input): edge for edge in edges.values()}
    pumps = set()
    for crystal in (c1, c2):
        assert kind(route(nodes, edges, crystal, "pump")[0]) == "beam_block"
        node = nodes[incoming[crystal.id, "in"].source]
        while kind(node) == "mirror":
            node = nodes[incoming[node.id, "in"].source]
        assert kind(node) == "beamsplitter" and node.id != bell1.id
        pumps.add(node.id)
    assert len(pumps) == 1
    pump_splitter = pumps.pop()
    assert kind(nodes[incoming[pump_splitter, "primary"].source]) == "laser"


def test_cross_output_bell_projection_swaps_two_singlets():
    # Balanced NPBS creation-operator maps: a† -> (c† + i*d†)/sqrt(2),
    # b† -> (i*c† + d†)/sqrt(2), independently of H/V polarization.
    def coincidences(state):
        amplitudes = dict.fromkeys(product(range(2), repeat=2), 0j)
        for (i, j), coefficient in state.items():
            for c_pol, d_pol, amplitude in ((i, j, .5), (j, i, -.5)):
                amplitudes[c_pol, d_pol] += coefficient * amplitude
        return amplitudes

    r = 1 / math.sqrt(2)
    singlet = {(0, 1): 1 / math.sqrt(2), (1, 0): -1 / math.sqrt(2)}
    triplets = ({(0, 1): r, (1, 0): r}, {(0, 0): r, (1, 1): r},
                {(0, 0): r, (1, 1): -r})
    assert sum(abs(a) ** 2 for a in coincidences(singlet).values()) == pytest.approx(1)
    for state in triplets:
        assert sum(abs(a) ** 2 for a in coincidences(state).values()) == pytest.approx(0)

    # The detectors do not resolve polarization. Both orthogonal coincidence
    # patterns must leave the same remote singlet (up to a global phase).
    total = 0
    for clicks in ((0, 1), (1, 0)):
        outer = {
            (a, d): sum(singlet.get((a, b), 0) * coincidences({(b, c): 1})[clicks]
                        * singlet.get((c, d), 0) for b, c in product(range(2), repeat=2))
            for a, d in product(range(2), repeat=2)
        }
        probability = sum(abs(amplitude) ** 2 for amplitude in outer.values())
        total += probability
        assert probability == pytest.approx(0.125)
        assert outer[0, 0] == outer[1, 1] == 0
        assert outer[0, 1] == pytest.approx(-outer[1, 0])
        assert abs(outer[0, 1]) / math.sqrt(probability) == pytest.approx(r)
    assert total == pytest.approx(0.25)
