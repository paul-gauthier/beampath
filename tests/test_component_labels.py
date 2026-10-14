import pytest

from beampath import ComponentError, HWP, component, components


@pytest.mark.parametrize("name", components.__all__)
@pytest.mark.parametrize("parts", [
    ("First", "Second", "Third"),
    ("First\nDetail", "Second\nMore detail", "Third"),
    ("", "Second", ""),
])
def test_all_component_factories_accept_label_lines(name, parts):
    parameters = {"turn": "left"} if name == "mirror" else {}
    expected = "\n".join(parts)
    spec = getattr(components, name)(*parts, **parameters)
    assert spec.label == expected
    assert spec == component(name, *parts, **spec.parameters)
    assert spec == getattr(components, name)(expected, **parameters)


@pytest.mark.parametrize("name", components.__all__)
def test_default_hidden_and_keyword_labels_are_preserved(name):
    factory = getattr(components, name)
    parameters = {"turn": "left"} if name == "mirror" else {}
    default = factory(**parameters)
    assert default.label is None
    assert factory(None, **parameters) == default
    assert factory(None, "Model", **parameters).display_label == default.display_label + "\nModel"
    assert factory("", **parameters).display_label == ""
    assert factory(label="Custom\nModel", **parameters) == factory("Custom", "Model", **parameters)


@pytest.mark.parametrize("name,parameters", [
    ("beamsplitter", {"turn": "right"}),
    ("PBS", {"turn": "right"}),
    ("fiber_splitter", {"turn": "right"}),
    ("fiber_launch", {"heading": "north"}),
    ("fiber_coupler", {"heading": "south"}),
    ("mirror", {"angle": -32}),
    ("mirror", {"heading": "north"}),
    ("mirror", {"turn": "right"}),
    ("spdc", {"opening_angle": 30}),
])
def test_label_lines_preserve_component_options(name, parameters):
    spec = getattr(components, name)("First", "Second", **parameters)
    assert spec == component(name, "First\nSecond", **parameters)
    assert dict(spec.parameters) == parameters


@pytest.mark.parametrize("parts", [
    (123,), (123, "Model"), ("First", None), ("First", 123),
    ("First", ["Model"]), ("First", "Second", False),
])
def test_invalid_label_parts_raise_component_error(parts):
    with pytest.raises(ComponentError, match="Label"):
        HWP(*parts)
    with pytest.raises(ComponentError, match="Label"):
        component("HWP", *parts)
