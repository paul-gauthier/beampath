"""Render the hello diagram with a grey code inset for social media.

Run with the PNG dependencies installed. On macOS with Homebrew Cairo:
    DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/python scripts/render_hello_social.py
"""
from io import StringIO
import json
import keyword
from pathlib import Path
import re
import tokenize
import xml.etree.ElementTree as ET

from beampath.examples.hello import build
from beampath.render import _png_metadata, element, number, tag


PROJECT = Path(__file__).resolve().parents[1]
WIDTH, HEIGHT = 2400, 1260


def build_social_svg():
    """Preserve the original optics and add editable, highlighted SVG text."""
    readme = (PROJECT / "README.md").read_text(encoding="utf-8")
    code = re.search(
        r"<!-- README:BEGIN hello -->\n```python\n(.*?)\n```",
        readme, re.DOTALL,
    ).group(1)
    root = ET.fromstring(build().to_svg())
    x, y, _, height = map(float, root.get("viewBox").split())
    width = height * WIDTH / HEIGHT
    root.set("width", str(WIDTH))
    root.set("height", str(HEIGHT))
    root.set("viewBox", " ".join(number(v) for v in (x, y, width, height)))
    root.set("aria-label", "Hello optical setup with its Python sample code")
    root.find(f"{tag('rect')}[@id='background']").set("width", number(width))
    manifest_node = root.find(
        f"{tag('metadata')}/{tag('metadata')}[@id='asset-attribution-manifest']"
    )
    manifest = json.loads(manifest_node.text)
    manifest["bounds"] = [x, y, x + width, y + height]
    manifest_node.text = json.dumps(manifest, ensure_ascii=False, indent=2)
    element(root, "title").text = "beampath — hello"
    element(root, "desc").text = (
        "A fiber launch, two mirrors, a half-wave plate, and a fiber coupler, "
        "with the Python code that creates the diagram in the upper right."
    )

    panel_x, panel_y = 335, y + 38
    panel_width, panel_height = x + width - panel_x - 38, 344
    inset = element(root, "g", id="sample-code-inset")
    element(inset, "rect", x=number(panel_x), y=number(panel_y),
            width=number(panel_width), height=panel_height, rx=8,
            fill="#eceef0")
    text_group = element(inset, "g", id="sample-code", font_size=24,
                         font_family="Menlo, DejaVu Sans Mono, monospace",
                         fill="#24292f")

    # Retain whitespace and code as text; token spans only change its color.
    highlights = {}
    for token in tokenize.generate_tokens(StringIO(code).readline):
        color = None
        if token.type == tokenize.STRING:
            color = "#b4232e"
        elif token.type == tokenize.NAME and keyword.iskeyword(token.string):
            color = "#7c3aae"
        if color:
            row, start = token.start
            highlights.setdefault(row, []).append((start, token.end[1], color))

    for row, line in enumerate(code.splitlines(), start=1):
        text = element(text_group, "text", x=number(panel_x + 28),
                       y=number(panel_y + 44 + (row - 1) * 29),
                       **{"xml:space": "preserve"})
        cursor = 0
        for start, end, color in highlights.get(row, []):
            if cursor < start:
                element(text, "tspan").text = line[cursor:start]
            element(text, "tspan", fill=color).text = line[start:end]
            cursor = end
        if cursor < len(line):
            element(text, "tspan").text = line[cursor:]

    ET.indent(root, space="  ")
    # Pretty-printing must not add visible whitespace inside preserved code.
    for text in text_group:
        text.text = ""
        for span in text:
            span.tail = ""
    return '<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


def main():
    import cairosvg

    svg = build_social_svg()
    output = PROJECT / "examples" / "images"
    (output / "hello-social.svg").write_text(svg, encoding="utf-8")
    png = cairosvg.svg2png(bytestring=svg.encode("utf-8"),
                          output_width=WIDTH, output_height=HEIGHT)
    (output / "hello-social.png").write_bytes(_png_metadata(png, svg, 96))
    print(f"Created {output / 'hello-social.svg'}")
    print(f"Created {output / 'hello-social.png'} ({WIDTH} × {HEIGHT})")


if __name__ == "__main__":
    main()
