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
        assert "beampath/py.typed" in archive.namelist()
    code = """
import sys
import runpy
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import beampath
from beampath.examples import cage_system, mzi
assert Path(beampath.__file__).is_relative_to(Path(sys.argv[1]))
assert 'cairosvg' not in sys.modules
for setup in (cage_system(), mzi()):
    svg = setup.to_svg()
    assert 'CC BY' in svg or 'Creative Commons Attribution' in svg
    assert 'data-component' in svg
assert 'cairosvg' not in sys.modules
for name, factory in (("cage", cage_system), ("mzi", mzi)):
    sys.argv = ["beampath.examples", "--diagram", name, "--output-dir", "examples"]
    runpy.run_module("beampath.examples", run_name="__main__")
    assert Path("examples", name + ".svg").read_text() == factory().to_svg()
"""
    subprocess.run([sys.executable, "-I", "-c", code, str(installation)],
                   cwd=tmp_path, check=True, capture_output=True, text=True)
