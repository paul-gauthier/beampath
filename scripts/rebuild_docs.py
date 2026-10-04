"""Refresh selected documentation snippets and all example PNG previews."""
import ast
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
from textwrap import dedent

from beampath.examples.__main__ import EXAMPLES


PROJECT = Path(__file__).resolve().parents[1]
DOCUMENTS = ("README.md", "docs/guide.md", "docs/reference.md", "docs/development.md")
# Only examples embedded in documentation need a standalone export statement.
SAVE_CALLS = {
    "hello": 'setup.save("hello.svg")',
    "mzi": 'mzi.save("mzi.svg")',
    "reuse": 'path.save("reuse.svg")',
    "rendering": 'path.save("rendering.png", style=STYLE, width=2400, dpi=600)',
    "custom_component": 'fork.save("custom_component.svg")',
    "mixed_fiber": 'setup.save("mixed_fiber.svg")',
    "spdc": 'source.save("spdc.svg")',
    "spdc_collinear": 'source.save("spdc_collinear.svg")',
}
DOCS_MARKER = re.compile(r"<!-- DOCS:(BEGIN|END) ([a-z][a-z0-9_]*) -->")


def extract_snippet(source, filename):
    """Join individually dedented source regions, excluding the markers."""
    regions = []
    start = None
    lines = source.splitlines(keepends=True)
    for index, line in enumerate(lines):
        marker = line.strip()
        if not marker.startswith("# DOCS:"):
            continue
        location = f"{filename}:{index + 1}"
        if marker == "# DOCS:BEGIN" and start is None:
            start = index + 1
        elif marker == "# DOCS:END" and start is not None:
            region = dedent("".join(lines[start:index])).strip("\n")
            if not region.strip():
                raise ValueError(f"{location}: empty documentation region")
            regions.append(region)
            start = None
        else:
            raise ValueError(f"{location}: invalid or unpaired DOCS marker")
    if start is not None:
        raise ValueError(f"{filename}:{start}: missing # DOCS:END")
    if not regions:
        raise ValueError(f"{filename}: no DOCS regions")
    return "\n\n".join(regions)


def update_document(document, project, filename):
    """Replace example blocks while preserving everything outside them."""
    result = []
    active = None
    seen = set()
    for number, line in enumerate(document.splitlines(keepends=True), start=1):
        if line.lstrip().startswith("<!-- DOCS:"):
            marker = DOCS_MARKER.fullmatch(line.rstrip("\r\n"))
            if marker is None:
                raise ValueError(f"{filename}:{number}: malformed DOCS marker")
            kind, name = marker.groups()
            if kind == "BEGIN":
                if active is not None or name in seen or name not in SAVE_CALLS or name not in EXAMPLES:
                    raise ValueError(f"{filename}:{number}: nested, duplicate, or unknown example {name}")
                active = name
                result.append(line)
            else:
                if active != name:
                    raise ValueError(f"{filename}:{number}: unpaired end marker for {name}")
                source = project / "examples" / f"{name}.py"
                code = extract_snippet(source.read_text(encoding="utf-8"), source)
                code += "\n" + SAVE_CALLS[name]
                try:
                    ast.parse(code, filename=str(source))
                except SyntaxError as exc:
                    raise ValueError(f"{source}: invalid documentation snippet: {exc}") from exc
                result.extend(["```python\n", code, "\n```\n", line])
                seen.add(name)
                active = None
        elif active is None:
            result.append(line)
    if active is not None:
        raise ValueError(f"{filename}: missing end marker for {active}")
    return "".join(result)


def render_examples(project, output):
    result = subprocess.run(
        [sys.executable, "-m", "beampath.examples", "--diagram", "all", "--png",
         "--output-dir", str(output)],
        cwd=project, capture_output=True, text=True,
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit status {result.returncode}"
        detail = detail.splitlines()[-1]
        raise RuntimeError(
            f"Example rendering failed:\n{detail}\n"
            "PNG export requires beampath[png] and native Cairo. "
            "See docs/reference.md#cairo-troubleshooting for the macOS library-path setup."
        )


def write_if_changed(path, data):
    if not path.exists() or path.read_bytes() != data:
        path.write_bytes(data)


def rebuild_docs(project=PROJECT):
    project = project.resolve()
    # Validate every document and selected snippet before rendering or writing.
    documents = {
        project / name: update_document(
            (project / name).read_bytes().decode("utf-8"), project, name
        ).encode("utf-8")
        for name in DOCUMENTS
    }
    build = project / "build"
    build.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix="docs-", dir=build) as staging:
        output = Path(staging)
        render_examples(project, output)
        # Read every preview before replacing any tracked output.
        previews = {name: (output / f"{name}.png").read_bytes() for name in EXAMPLES}
        images = project / "examples" / "images"
        images.mkdir(exist_ok=True)
        for path, data in documents.items():
            write_if_changed(path, data)
        for name, data in previews.items():
            write_if_changed(images / f"{name}.png", data)


def main():
    try:
        rebuild_docs()
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Could not rebuild documentation: {exc}", file=sys.stderr)
        return 1
    print(f"Rebuilt {len(DOCUMENTS)} documentation pages and {len(EXAMPLES)} previews.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
