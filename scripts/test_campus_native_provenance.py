import hashlib
import json
import zipfile
from pathlib import Path

from audit_hill_block_artifact import audit_native_capture


def test_native_audit_detects_changed_world_and_screenshot(tmp_path):
    world = tmp_path / "study/world"
    (world / "region").mkdir(parents=True)
    (world / "level.dat").write_bytes(b"original metadata")
    region = world / "region/r.0.0.mca"
    region.write_bytes(b"original region")
    run = tmp_path / "run"
    run.mkdir()
    backup = run / "backup.zip"
    with zipfile.ZipFile(backup, "w") as z:
        for source in (world / "level.dat", region):
            z.write(source, "copied/" + source.relative_to(world).as_posix())
    (run / "launch-manifest.json").write_text(
        json.dumps(
            {
                "source_world": str(world),
                "preupgrade_backup": str(backup),
                "copied_world": str(run / "copied"),
            }
        )
    )
    views = []
    for i in range(4):
        shot = run / f"view{i}.png"
        shot.write_bytes(f"synthetic screenshot {i}".encode())
        views.append(
            {
                "name": str(i),
                "screenshot": str(shot),
                "sha256": hashlib.sha256(shot.read_bytes()).hexdigest(),
            }
        )
    report = run / "report.json"
    report.write_text(
        json.dumps(
            {"status": "complete", "capture_input_probe_passed": True, "views": views}
        )
    )
    native, errors = audit_native_capture(world.parent, report)
    assert errors == [] and native["source_files_matched_to_preupgrade_backup"] == 2
    region.write_bytes(b"different source")
    Path(views[0]["screenshot"]).write_bytes(b"different image")
    _, errors = audit_native_capture(world.parent, report)
    assert any("pre-upgrade world differs" in e for e in errors)
    assert any("screenshot missing or changed" in e for e in errors)
