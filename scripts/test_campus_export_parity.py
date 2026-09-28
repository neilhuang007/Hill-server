import numpy as np
import pytest
from campus_export_parity import read_archive, compare_world, role_histogram
from test_audit_hill_chapel_sample import _SyntheticStudy


@pytest.mark.parametrize(
    "mutation,failed_count",
    [
        ("none", None),
        ("remove_expected", "extra_count"),
        ("append_expected", "missing_count"),
        ("duplicate_expected", "duplicate_npz_coordinate_count"),
        ("change_property", "state_mismatch_count"),
    ],
)
def test_section_comparison_detects_actual_serialized_failures(
    tmp_path, mutation, failed_count
):
    study = _SyntheticStudy(tmp_path)
    archive = read_archive(study.study_dir / "sample-blocks.npz")
    if mutation == "remove_expected":
        for key in ("coords", "state_ids", "role_ids"):
            archive[key] = archive[key][1:]
    elif mutation in {"append_expected", "duplicate_expected"}:
        coord = archive["coords"][:1].copy()
        if mutation == "append_expected":
            coord[0] = archive["coords"].max(axis=0) + [1, 0, 1]
        archive["coords"] = np.concatenate([archive["coords"], coord])
        for key in ("state_ids", "role_ids"):
            archive[key] = np.concatenate([archive[key], archive[key][:1]])
    elif mutation == "change_property":
        state = {
            "Name": "minecraft:gray_stained_glass_pane",
            "Properties": {
                "east": "false",
                "north": "true",
                "south": "false",
                "west": "false",
                "waterlogged": "false",
            },
        }
        study.replace_anvil_state((12, 2, 5), state)
    parity, errors, keys, chunks = compare_world(archive, study.study_dir / "world")
    assert chunks > 0 and keys
    assert sum(n for _, _, n in role_histogram(archive)) == len(archive["coords"])
    if failed_count:
        assert errors and parity[failed_count] == 1
    else:
        assert not errors
        assert parity["common_coordinates"] == len(archive["coords"])
