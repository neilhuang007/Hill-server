"""Copy one explicitly selected campus draft for new projects, leaving authoring data untouched."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def stage(draft, output):
    draft = draft.resolve(strict=True)
    output = output.resolve()
    if output.exists() or output.is_relative_to(draft):
        raise ValueError("Choose a new output directory outside the preserved draft.")
    manifest = json.loads((draft / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("blocks_per_metre") != 2:
        raise ValueError("Expected the measured campus frame at two blocks per metre.")
    x0, z0, x1, z1 = manifest["bounds_xz_blocks"]
    view = json.loads((draft / "quad-start.json").read_text(encoding="utf-8"))["views"][0]
    x, eye, z = view["eye"]
    source = draft / "world"
    if not (source / "level.dat").is_file() or not (source / "region").is_dir():
        raise ValueError("The selected draft is not an exported Java world.")
    output.mkdir(parents=True)
    shutil.copy2(source / "level.dat", output / "level.dat")
    for name in ("region", "poi"):
        if (source / name).is_dir():
            shutil.copytree(source / name, output / name)
    (output / "hill-campus-template.yml").write_text(
        f"revision: {draft.name}\nblocks-per-metre: 2\nblock-bounds: [{x0}, -64, {z0}, {x1-1}, 319, {z1-1}]\n"
        f"spawn: [{x}, {eye-1.62:.2f}, {z}]\n", encoding="utf-8")
    resources = Path(__file__).resolve().parents[1] / "src/main/resources"
    for name in ("hill-buildings.yml", "hill-areas.yml"):
        shutil.copy2(resources / name, output / name)
    records = {str(file.relative_to(output)).replace('\\', '/'): hashlib.sha256(file.read_bytes()).hexdigest()
               for file in sorted(output.rglob('*')) if file.is_file()}
    (output / "campus-source.json").write_text(json.dumps({"draft": draft.name,
        "selection": "Explicit operator selection for new projects", "files": records}, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared {draft.name} in {output}; original draft and existing student worlds are unchanged.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    stage(args.draft, args.output)
