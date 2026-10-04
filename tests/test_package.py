from pathlib import Path
import subprocess
import sys
import zipfile


def test_built_wheel_resources_work_without_checkout(tmp_path):
    project = Path(__file__).resolve().parents[1]
    wheels = tmp_path / "wheels"
    subprocess.run([sys.executable, "-m", "build", "--wheel", "--no-isolation", "--outdir", str(wheels)],
                   cwd=project, check=True, capture_output=True, text=True)
    wheel = next(wheels.glob("*.whl"))
    installation = tmp_path / "installation"
    with zipfile.ZipFile(wheel) as archive:
        archive.extractall(installation)
        assert "beampath/assets/LICENSE" in archive.namelist()
        assert "beampath/assets/f-power-meter.svg" in archive.namelist()
        assert "beampath/assets/fs-spdc.svg" in archive.namelist()
        assert "beampath/assets/fs-pbs-cube.svg" in archive.namelist()
        assert "beampath/assets/fs-detector.svg" in archive.namelist()
        assert "beampath/assets/fs-beam-block.svg" in archive.namelist()
        assert "beampath/py.typed" in archive.namelist()
        assert "beampath/components/mirror.py" in archive.namelist()
        assert "beampath/components/pbs.py" in archive.namelist()
        assert "beampath/examples/hello.py" in archive.namelist()
        assert "beampath/examples/custom_component.py" in archive.namelist()
        assert "beampath/examples/reuse.py" in archive.namelist()
        assert "beampath/examples/zwm.py" in archive.namelist()
        for name in ("hom", "chsh", "hbt", "swapping"):
            assert f"beampath/examples/{name}.py" in archive.namelist()
        for name in ("spdc_collinear", "shared_optic", "fiber_bends", "composition"):
            assert f"beampath/examples/{name}.py" not in archive.namelist()
    code = """
import sys
import runpy
from importlib import import_module
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import beampath
from beampath.examples._discovery import example_names
from beampath import nd_filter, bandpass_filter, fiber_laser, fiber_launch, fiber_coupler, fiber_power_meter
from beampath import beam_block, detector
from beampath import components

def example(name):
    return runpy.run_module("beampath.examples." + name)["setup"]

assert Path(beampath.__file__).is_relative_to(Path(sys.argv[1]))
assert 'cairosvg' not in sys.modules
assert 'pypdf' not in sys.modules
for name in components.__all__:
    module = import_module(getattr(components, name).__module__)
    assert module.demo().to_svg()
for setup in (example("cage"), example("mzi"), nd_filter() >> bandpass_filter(), example("mixed_fiber"), example("fiber_splitter"),
              fiber_laser() >> fiber_power_meter(),
              fiber_laser() >> fiber_launch() >> fiber_coupler() >> fiber_power_meter(),
              fiber_launch() >> detector(), fiber_launch() >> beam_block()):
    svg = setup.to_svg()
    assert 'CC BY' in svg or 'Creative Commons Attribution' in svg
    assert 'data-component' in svg
assert 'cairosvg' not in sys.modules
assert 'pypdf' not in sys.modules
for name in ("cage", "mzi"):
    sys.argv = ["beampath.examples", "--diagram", name, "--output-dir", "examples"]
    runpy.run_module("beampath.examples", run_name="__main__")
    assert Path("examples", name + ".svg").read_text() == example(name).to_svg()
sys.argv = ["beampath.examples", "--diagram", "all", "--output-dir", "all-examples"]
runpy.run_module("beampath.examples", run_name="__main__")
assert {p.stem for p in Path("all-examples").glob("*.svg")} == set(example_names())
assert 'cairosvg' not in sys.modules
assert 'pypdf' not in sys.modules
"""
    subprocess.run([sys.executable, "-I", "-c", code, str(installation)],
                   cwd=tmp_path, check=True, capture_output=True, text=True)
