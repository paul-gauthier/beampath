"""Editable SVG assembly and optional PNG conversion."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from importlib import resources
import json
from pathlib import Path
import re
import struct
import zlib
from collections.abc import Mapping
import xml.etree.ElementTree as ET

from .definitions import Artwork
from .geometry import clean, finite
from .layout import Layout, Style
from .model import Setup

SVG = "http://www.w3.org/2000/svg"
RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
CC = "http://creativecommons.org/ns#"
DC = "http://purl.org/dc/elements/1.1/"
for prefix, uri in (("", SVG), ("rdf", RDF), ("cc", CC), ("dc", DC)):
    ET.register_namespace(prefix, uri)


def tag(name):
    return f"{{{SVG}}}{name}"


def number(value):
    return f"{clean(value):.12g}"


def element(parent, name, **attributes):
    return ET.SubElement(parent, tag(name),
                         {key.replace("_", "-"): str(value) for key, value in attributes.items()})


def artwork_bytes(art: Artwork) -> bytes:
    if art.package_resource is not None:
        return resources.files("beampath").joinpath("assets", art.package_resource).read_bytes()
    if art.path is not None:
        return Path(art.path).read_bytes()
    return art.svg.encode("utf-8")


def _namespace_ids(node, prefix):
    mapping = {n.get("id"): f"{prefix}-{n.get('id')}" for n in node.iter() if n.get("id")}

    def refs(value):
        value = re.sub(r"url\(#([^)]*)\)", lambda m: f"url(#{mapping.get(m[1], m[1])})", value)
        if value.startswith("#") and value[1:] in mapping:
            value = "#" + mapping[value[1:]]
        return value

    for child in node.iter():
        for key, value in list(child.attrib.items()):
            child.set(key, mapping[value] if key == "id" else refs(value))
        if child.tag == tag("style") and child.text:
            child.text = refs(child.text)


def _json_value(value):
    if isinstance(value, Mapping):
        return {str(k): _json_value(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return [_json_value(v) for v in sorted(value, key=repr)]
    return value


def _png_metadata(data: bytes, svg: str, dpi: float) -> bytes:
    """Embed credits and resolution without requiring another image backend."""
    root = ET.fromstring(svg)
    credits = root.find(f"{tag('metadata')}/{tag('metadata')}[@id='asset-attribution-manifest']").text

    def chunk(kind, content):
        return struct.pack(">I", len(content)) + kind + content + struct.pack(">I", zlib.crc32(kind + content))

    pixels_per_meter = round(dpi / .0254)
    if not 0 < pixels_per_meter < 2**32:
        raise ValueError("DPI is outside the PNG resolution range")
    additions = chunk(b"pHYs", struct.pack(">IIB", pixels_per_meter, pixels_per_meter, 1))
    additions += chunk(b"iTXt", b"beampath-attribution\0\0\0\0\0" + credits.encode("utf-8"))
    result, cursor, inserted = data[:8], 8, False
    while cursor < len(data):
        length = struct.unpack(">I", data[cursor:cursor + 4])[0]
        kind = data[cursor + 4:cursor + 8]
        if kind == b"IDAT" and not inserted:
            result += additions
            inserted = True
        if kind != b"pHYs":
            result += data[cursor:cursor + length + 12]
        cursor += length + 12
    return result


def render_svg(layout: Layout) -> str:
    x0, y0, x1, y1 = layout.bounds
    style = layout.style
    svg = ET.Element(tag("svg"), {
        "version": "1.1", "width": number(x1 - x0), "height": number(y1 - y0),
        "viewBox": " ".join(number(v) for v in (x0, y0, x1 - x0, y1 - y0)),
        "font-family": style.font_family,
        "aria-label": f"Optical setup with {len(layout.placements)} components",
    })
    metadata = element(svg, "metadata", id="provenance")
    rdf = ET.SubElement(metadata, f"{{{RDF}}}RDF")
    manifest = {"schema_version": 1, "generator": "beampath", "assets": [], "optics": [],
                "segments": [], "labels": [], "bounds": layout.bounds}
    sources = {}
    for placed in layout.placements.values():
        definition = placed.instance.spec.definition
        if definition.name not in sources:
            art = definition.artwork
            data = artwork_bytes(art)
            source = ET.fromstring(data)
            if source.tag != tag("svg"):
                raise ValueError(f"{definition.name}: artwork must be an SVG document")
            sources[definition.name] = source
            asset = {"component": definition.name, "source_url": art.source_url,
                     "sha256": sha256(data).hexdigest(), "license_url": art.license_url,
                     "attribution": art.attribution, "source_center": art.center,
                     "scale": art.scale, "adaptations":
                     "Selected source primitives; similarity transforms; upright text; namespaced IDs."}
            manifest["assets"].append(asset)
            if art.attribution:
                work = ET.SubElement(rdf, f"{{{CC}}}Work", {f"{{{RDF}}}about": definition.name})
                ET.SubElement(work, f"{{{DC}}}description").text = art.attribution
                if art.source_url:
                    ET.SubElement(work, f"{{{DC}}}source", {f"{{{RDF}}}resource": art.source_url})
                if art.license_url:
                    ET.SubElement(work, f"{{{CC}}}license", {f"{{{RDF}}}resource": art.license_url})
    defs = element(svg, "defs")
    # Same arrow geometry as the source library, recolored for custom beam styles.
    marker = element(defs, "marker", id="beam-arrow", markerWidth=6, markerHeight=4,
                     refX=6, refY=2, orient="auto")
    element(marker, "polygon", points="0,0 6,2 0,4", fill=style.beam_color)
    element(svg, "rect", id="background", x=number(x0), y=number(y0),
            width=number(x1 - x0), height=number(y1 - y0), fill=style.background)
    beams = element(svg, "g", id="optical-path", fill="none", stroke=style.beam_color,
                    stroke_width=number(style.beam_width), stroke_linecap="butt")
    for segment in layout.segments:
        element(beams, "line", id=segment.id,
                x1=number(segment.start[0]), y1=number(segment.start[1]),
                x2=number(segment.end[0]), y2=number(segment.end[1]),
                data_source=segment.source, data_output=segment.output,
                data_target=segment.target or "", data_input=segment.input or "")
        dx = (segment.end[0] - segment.start[0]) / segment.length
        dy = (segment.end[1] - segment.start[1]) / segment.length
        mx, my = ((segment.start[i] + segment.end[i]) / 2 for i in (0, 1))
        arrow_length = min(12, segment.length / 4)
        element(beams, "line", id=f"{segment.id}-arrow",
                x1=number(mx - arrow_length * dx), y1=number(my - arrow_length * dy),
                x2=number(mx), y2=number(my), marker_end="url(#beam-arrow)")
        manifest["segments"].append({"id": segment.id, "start": segment.start, "end": segment.end,
                                     "source": segment.source, "output": segment.output,
                                     "target": segment.target, "input": segment.input})

    components = element(svg, "g", id="components")
    for placed in layout.placements.values():
        node = placed.instance
        art = node.spec.definition.artwork
        angle = node.heading + node.spec.geometry.artwork_rotation
        transform = (f"translate({number(placed.position[0])} {number(placed.position[1])}) "
                     f"rotate({number(angle)}) scale({number(art.scale)}) ")
        if node.spec.geometry.reflected:
            transform += "scale(-1 1) "
        transform += f"translate({number(-art.center[0])} {number(-art.center[1])})"
        group = element(components, "g", id=node.id, transform=transform,
                        data_component=node.spec.definition.name,
                        data_optical_center=" ".join(number(v) for v in placed.position),
                        data_heading=number(node.heading))
        source = deepcopy(sources[node.spec.definition.name])
        for attribute in ("font-family", "fill", "stroke", "stroke-width"):
            if attribute in source.attrib:
                group.set(attribute, source.attrib[attribute])
        _namespace_ids(source, node.id)
        source_ids = {child.get("id") for child in source.iter() if child.get("id")}
        for index, child in enumerate(source):
            if child.tag != tag("defs") and art.selector is not None and not art.selector(child):
                continue
            if child.get("id") is None:
                child_id = f"{node.id}-source-{index:02d}"
                while child_id in source_ids:
                    child_id += "-generated"
                child.set("id", child_id)
                source_ids.add(child_id)
            for text in child.iter(tag("text")):
                # Counteract the placement transform at the text's own anchor.
                # Artwork geometry and the glyph's position still transform normally.
                tx, ty = float(text.get("x", 0)), float(text.get("y", 0))
                compensation = f"translate({number(tx)} {number(ty)}) "
                if node.spec.geometry.reflected:
                    compensation += "scale(-1 1) "
                compensation += f"rotate({number(-angle)}) translate({number(-tx)} {number(-ty)})"
                existing = text.get("transform", "")
                text.set("transform", compensation + (" " + existing if existing else ""))
            group.append(child)
        manifest["optics"].append({"id": node.id, "component": node.spec.definition.name,
                                  "label": node.spec.display_label, "parameters": _json_value(node.spec.parameters),
                                  "position": placed.position, "heading": node.heading,
                                  "artwork_rotation": angle,
                                  "reflected": node.spec.geometry.reflected,
                                  "transform": transform})
    labels = element(svg, "g", id="component-labels", font_size=number(style.font_size),
                     font_weight="normal", text_anchor="middle", fill="#000000")
    for label in layout.labels:
        element(labels, "text", id=f"{label.optic}-label", x=number(label.position[0]),
                y=number(label.position[1])).text = label.text
        manifest["labels"].append({"optic": label.optic, "text": label.text, "position": label.position})
    element(metadata, "metadata", id="asset-attribution-manifest").text = json.dumps(manifest, ensure_ascii=False, indent=2)
    ET.indent(svg, space="  ")
    return '<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(svg, encoding="unicode") + "\n"


def save(setup: Setup, filename: str | Path, *, style: Style | None = None,
         width: int | None = None, dpi: float = 96) -> Path:
    filename = Path(filename)
    suffix = filename.suffix.lower()
    if suffix not in {".svg", ".png"}:
        raise ValueError("Output filename must end in .svg or .png")
    if width is not None and (not isinstance(width, int) or isinstance(width, bool) or width <= 0):
        raise ValueError("PNG width must be a positive integer")
    dpi = finite(dpi, "dpi")
    if dpi <= 0:
        raise ValueError("DPI must be positive")
    if suffix == ".svg" and width is not None:
        raise ValueError("width is a PNG export option")
    svg = setup.to_svg(style=style)
    if suffix == ".svg":
        filename.write_text(svg, encoding="utf-8")
    else:
        try:
            import cairosvg
        except (ImportError, OSError) as exc:
            raise RuntimeError("PNG export requires beampath[png] and a discoverable native Cairo library") from exc
        data = cairosvg.svg2png(bytestring=svg.encode("utf-8"), output_width=width, dpi=dpi)
        data = _png_metadata(data, svg, dpi)
        filename.write_bytes(data)
    return filename
