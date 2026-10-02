"""Refresh marked README snippets and regenerate their PNG previews."""
import ast
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
from textwrap import dedent


PROJECT = Path(__file__).resolve().parents[1]
SAVE_CALLS = {
    "hello": 'setup.save("hello.svg")',
    "cage": 'setup.save("setup.svg")',
    "mirror_heading": 'setup.save("mirror_heading.svg")',
    "mzi": 'split.save("mzi.svg")',
    "shared_optic": 'split.save("shared_optic.svg")',
    "reuse": 'path.save("reuse.svg")',
    "rendering": 'path.save("rendering.png", style=STYLE, width=2400, dpi=600)',
    "custom_component": 'fork.save("custom_component.svg")',
}
README_MARKER = re.compile(r"<!-- README:(BEGIN|END) ([a-z][a-z0-9_]*) -->")


def extract_snippet(source, filename):
    """Join individually dedented source regions, excluding the markers."""
    regions = []
    start = None
    lines = source.splitlines(keepends=True)
    for index, line in enumerate(lines):
        marker = line.strip()
        if not marker.startswith("# README:"):
            continue
        location = f"{filename}:{index + 1}"
        if marker == "# README:BEGIN" and start is None:
            start = index + 1
        elif marker == "# README:END" and start is not None:
            region = dedent("".join(lines[start:index])).strip("\n")
            if not region.strip():
                raise ValueError(f"{location}: empty README region")
            regions.append(region)
            start = None
        else:
            raise ValueError(f"{location}: invalid or unpaired README marker")
    if start is not None:
        raise ValueError(f"{filename}:{start}: missing # README:END")
    if not regions:
        raise ValueError(f"{filename}: no README regions")
    return "\n\n".join(regions)


def update_readme(readme, project):
    """Replace example blocks while preserving everything outside them."""
    result = []
    active = None
    seen = set()
    for number, line in enumerate(readme.splitlines(keepends=True), start=1):
        if line.lstrip().startswith("<!-- README:"):
            marker = README_MARKER.fullmatch(line.rstrip("\r\n"))
            if marker is None:
                raise ValueError(f"README.md:{number}: malformed README marker")
            kind, name = marker.groups()
            if kind == "BEGIN":
                if active is not None or name in seen or name not in SAVE_CALLS:
                    raise ValueError(f"README.md:{number}: nested, duplicate, or unknown example {name}")
                active = name
                result.append(line)
            else:
                if active != name:
                    raise ValueError(f"README.md:{number}: unpaired end marker for {name}")
                source = project / "examples" / f"{name}.py"
                code = extract_snippet(source.read_text(encoding="utf-8"), source)
                code += "\n" + SAVE_CALLS[name]
                try:
                    ast.parse(code, filename=str(source))
                except SyntaxError as exc:
                    raise ValueError(f"{source}: invalid README snippet: {exc}") from exc
                result.extend(["```python\n", code, "\n```\n", line])
                seen.add(name)
                active = None
        elif active is None:
            result.append(line)
    if active is not None:
        raise ValueError(f"README.md: missing end marker for {active}")
    missing = SAVE_CALLS.keys() - seen
    if missing:
        raise ValueError(f"README.md: missing example blocks: {', '.join(sorted(missing))}")
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
            "See README's Rendering section for the macOS library-path setup."
        )


def write_if_changed(path, data):
    if not path.exists() or path.read_bytes() != data:
        path.write_bytes(data)


def rebuild_readme(project=PROJECT):
    project = project.resolve()
    readme_path = project / "README.md"
    updated = update_readme(readme_path.read_bytes().decode("utf-8"), project)
    build = project / "build"
    build.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix="readme-", dir=build) as staging:
        output = Path(staging)
        render_examples(project, output)
        # Read every preview before replacing any tracked output.
        previews = {name: (output / f"{name}.png").read_bytes() for name in SAVE_CALLS}
        images = project / "examples" / "images"
        images.mkdir(exist_ok=True)
        write_if_changed(readme_path, updated.encode("utf-8"))
        for name, data in previews.items():
            write_if_changed(images / f"{name}.png", data)


def main():
    try:
        rebuild_readme()
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Could not rebuild README: {exc}", file=sys.stderr)
        return 1
    print(f"Rebuilt README.md and {len(SAVE_CALLS)} previews.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
