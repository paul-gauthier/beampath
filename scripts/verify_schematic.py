#!/usr/bin/env python3
"""Verify generated examples, bundled artwork provenance, and optional raster output."""
import argparse
from hashlib import sha256
from importlib import resources
from io import BytesIO
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from beampath.examples import cage_system, mzi
from beampath.render import tag

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diagram", choices=("cage", "mzi"), default="cage")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "build/examples")
    parser.add_argument("--png", action="store_true")
    parser.add_argument("--width", type=int, default=7200)
    args = parser.parse_args()
    setup = mzi() if args.diagram == "mzi" else cage_system()
    name = "mzi" if args.diagram == "mzi" else "thorlabs_cage_system"
    svg = (args.output_dir / (name + ".svg")).read_text()
    if svg != setup.to_svg():
        raise AssertionError("Generated SVG differs from a fresh DSL rendering")
    root = ET.fromstring(svg)
    ids = [node.get("id") for node in root.iter() if node.get("id")]
    if len(ids) != len(set(ids)):
        raise AssertionError("SVG IDs are not unique")
    manifest = json.loads(root.find(f"{tag('metadata')}/{tag('metadata')}[@id='asset-attribution-manifest']").text)
    if len(manifest["optics"]) != len(setup.setup.optics):
        raise AssertionError("Physical optic count differs from graph")
    pinned = json.loads(resources.files("beampath").joinpath("assets/provenance.json").read_text())
    for asset in pinned["assets"]:
        data = resources.files("beampath").joinpath("assets", asset["file"]).read_bytes()
        if sha256(data).hexdigest() != asset["sha256"]:
            raise AssertionError(f"Bundled source changed: {asset['file']}")
    if args.png:
        import cairosvg
        from PIL import Image
        delivered = Image.open(args.output_dir / (name + ".png"))
        fresh = Image.open(BytesIO(cairosvg.svg2png(bytestring=svg.encode(), output_width=args.width, dpi=600)))
        if delivered.size != fresh.size or delivered.tobytes() != fresh.tobytes():
            raise AssertionError("PNG differs from a fresh SVG rasterization")
        if json.loads(delivered.info["beampath-attribution"]) != manifest:
            raise AssertionError("PNG does not retain its SVG attribution")
    print(f"PASS: {name} geometry, source hashes, IDs, credits" + (" and PNG pixels" if args.png else ""))


if __name__ == "__main__":
    main()
