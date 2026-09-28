# Campus reconstruction tools

These scripts create and audit campus source worlds; they are not required to
build the Paper plugin. **Construction is paused.** Read the
[workspace guide](../docs/workspace-layout.md) before generating or moving inputs.
Server installation, backup, and smoke tools are now in [ops/](../ops/README.md).

| Tool family | Purpose |
| --- | --- |
| `run_chapel_native_qa.py`, `launch_hill_campus_12111.py`, `chapel-native-qa/` | Native launch and screenshot evidence |
| `assemble_hill_campus_studies.py`, `refine_hill_campus_environment.py` | Combined assembly and environment refinement |
| `build_*`, `prepare_*`, `hill_*_details.py` | Measured building/site generation |
| `campus_*` | Shared geometry, materials, export, paving, artifact helpers |
| `audit_*`, `prove_*`, `inspect_*` | Geometry, provenance, routes, acceptance |
| `test_*.py`, `../tests/` | Reconstruction regression tests |
| `render_*`, `capture_bluemap_qa.py` | Visual review tooling |
| `generate-hill-campus.py`, `*voxelearth*`, `*roofer*` | Earlier pipelines retained for provenance/dependencies |

Preserve script paths: immutable studies record them and import helpers. Revision
age does not make a dependency obsolete. GIS dependencies are listed in
`requirements-hill-campus.txt`; some tests additionally need local reference data.
Never write into an accepted revision or active player save.
