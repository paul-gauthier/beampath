from pathlib import Path
import json
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest


EXAMPLES = {
    "hello": 5,
    "cage": 13,
    "mirror_heading": 3,
    "mzi": 10,
    "shared_optic": 10,
    "reuse": 8,
    "rendering": 3,
    "custom_component": 4,
}
SVG = "{http://www.w3.org/2000/svg}"


@pytest.mark.parametrize("name,count", EXAMPLES.items())
def test_example_scripts_run_from_another_directory(tmp_path, name, count):
    project = Path(__file__).resolve().parents[1]
    destination = tmp_path / "output"
    subprocess.run(
        [sys.executable, str(project / "examples" / f"{name}.py"),
         "--output-dir", str(destination)],
        cwd=tmp_path, check=True, capture_output=True, text=True,
    )
    assert sorted(p.name for p in destination.iterdir()) == [f"{name}.svg"]
    root = ET.parse(destination / f"{name}.svg").getroot()
    assert len(root.find(f"{SVG}g[@id='components']")) == count
    assert root.find(f"{SVG}g[@id='optical-path']").get("stroke") == (
        "#1f77b4" if name == "rendering" else "#CC0000"
    )


def test_all_examples_export_png_with_requested_width_and_credits(tmp_path):
    try:
        import cairosvg
    except (ImportError, OSError):
        pytest.skip("Optional PNG converter or native Cairo is unavailable")
    from PIL import Image

    subprocess.run(
        [sys.executable, "-m", "beampath.examples", "--diagram", "all", "--png",
         "--width", "640", "--output-dir", str(tmp_path)],
        cwd=tmp_path, check=True, capture_output=True, text=True,
    )
    assert {p.stem for p in tmp_path.glob("*.svg")} == set(EXAMPLES)
    assert {p.stem for p in tmp_path.glob("*.png")} == set(EXAMPLES)
    for name, count in EXAMPLES.items():
        with Image.open(tmp_path / f"{name}.png") as image:
            assert image.width == 640
            assert image.info["dpi"] == pytest.approx((600, 600), abs=.02)
            manifest = json.loads(image.info["beampath-attribution"])
            assert len(manifest["optics"]) == count
            assert all(asset["attribution"] for asset in manifest["assets"])
