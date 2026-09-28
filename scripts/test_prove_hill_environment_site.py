"""Cell-proof guards must reject altered or overly broad site exceptions."""

import copy

import pytest

from prove_hill_environment_site import classify_cell, require_complete_report, signature


AIR = {"Name":"minecraft:air"}
LEAF = {"Name":"minecraft:oak_leaves","Properties":{"persistent":"true","distance":"1","waterlogged":"false"}}


def evidence():
    cell = {"study":"ryan","xyz":[209,87,76],"expected":AIR,"actual":LEAF}
    mutation = {"xyz":[209,87,76],"before":AIR,"before_role":"air","after":LEAF,"after_role":"vegetation","feature":"registered_bed"}
    return dict(cell=cell,before_state=AIR,before_role="air",after_state=LEAF,
                after_role="vegetation",source_state=AIR,source_role="air",
                original_column_roles={"air","terrain"},final_column_roles={"air","terrain","vegetation"},
                journal={(209,87,76):mutation},authorized_xz={(209,76)},inherited=set())


def test_exact_authorized_journal_cell_passes():
    assert classify_cell(**evidence()) == "environment_journal"


@pytest.mark.parametrize("mutation", [
    lambda a:a.update(authorized_xz=set()),
    lambda a:a["journal"][(209,87,76)].update(after=AIR),
    lambda a:a["journal"][(209,87,76)].update(before_role="terrain"),
    lambda a:a.update(source_state=LEAF),
    lambda a:a.update(original_column_roles={"air","terrain","roof"}),
    lambda a:a.update(final_column_roles={"air","terrain","lighting"}),
    lambda a:a.update(source_role="floor"),
])
def test_no_mask_architecture_or_state_exceptions(mutation):
    args = copy.deepcopy(evidence())
    mutation(args)
    with pytest.raises(ValueError):
        classify_cell(**args)


def test_inherited_proof_requires_exact_untouched_signature():
    args = evidence()
    args.update(journal={},before_state=LEAF,before_role="vegetation",inherited={signature(args["cell"])})
    assert classify_cell(**args) == "inherited_untouched"
    args["before_role"] = "air"
    with pytest.raises(ValueError,match="changed without"):
        classify_cell(**args)


def test_prior_signature_does_not_authorize_new_unlisted_mutation():
    args = evidence()
    args.update(inherited={signature(args["cell"])},authorized_xz=set())
    with pytest.raises(ValueError,match="explicit authorized"):
        classify_cell(**args)


@pytest.mark.parametrize("role,state",[
    ("furniture",{"Name":"minecraft:oak_stairs","Properties":{"facing":"north","half":"top","shape":"straight","waterlogged":"false"}}),
    ("lighting",{"Name":"minecraft:lantern","Properties":{"hanging":"false","waterlogged":"false"}}),
    ("fixture",{"Name":"minecraft:bell","Properties":{"attachment":"ceiling","facing":"north","powered":"false"}}),
])
def test_exact_registered_new_fixture_is_eligible(role,state):
    args=evidence()
    args.update(after_state=state,after_role=role,final_column_roles={"air","terrain",role},registered_fixture_xyz={(209,87,76)},final_fixture_xyz={(209,87,76)})
    args["cell"]["actual"]=state
    args["journal"][(209,87,76)].update(after=state,after_role=role)
    assert classify_cell(**args)=="environment_journal"
    args["final_fixture_xyz"].add((209,88,76))
    with pytest.raises(ValueError,match="Unexplained final fixture"):
        classify_cell(**args)


def test_new_fixture_without_registered_source_footprint_is_rejected():
    args=evidence()
    args.update(after_role="lighting",final_column_roles={"air","terrain","lighting"},final_fixture_xyz={(209,87,76)})
    args["journal"][(209,87,76)]["after_role"]="lighting"
    with pytest.raises(ValueError,match="Unexplained final fixture"):
        classify_cell(**args)


def test_truncated_raw_report_is_rejected():
    with pytest.raises(ValueError,match="truncated"):
        require_complete_report({"format":"hill-integrated-study-audit-v1","manifest_sha256":"bound",
                                 "different_cells":{"ryan":2},"examples":[evidence()["cell"]]},"bound","raw")


@pytest.mark.parametrize("new_state,new_role",[
    (LEAF,"vegetation"),
    ({"Name":"minecraft:bell","Properties":{"attachment":"ceiling","facing":"north","powered":"false"}},"fixture"),
])
def test_complete_proof_reaudits_exact_inherited_and_new_site_cells(tmp_path,monkeypatch,new_state,new_role):
    """Exercise real archives, full comparisons and preservation audit together."""
    import json
    import shutil
    from pathlib import Path
    from assemble_hill_campus_studies import prepare_component
    from audit_hill_environment_revision import audit as preservation_audit
    from audit_hill_integrated_studies import audit as study_audit
    from build_hill_chapel_sample import Canvas
    from campus_study_io import digest,write_json
    import prove_hill_environment_site as prover

    monkeypatch.setattr(prover,"ROOT",tmp_path)
    monkeypatch.chdir(tmp_path)
    study=tmp_path/"study"; study.mkdir()
    write_json(study/"manifest.json",{"blocks_per_metre":2,"vertical_offset_m":-25})
    write_json(study/"profile.json",{"vertical_offset_m":-25})
    c=Canvas(0,0,8,8,2)
    for x in range(8):
        for z in range(8): c.set(x,80,z,"grass_block","terrain")
    c.set(5,81,5,"bricks","facade")
    c.export(study/"sample-blocks.npz")
    component=prepare_component(study,tmp_path/"runtime/campus-reconstruction/component-cache",2,-25,.5)
    base=tmp_path/"base"; final=tmp_path/"final"
    for d in (base,final): (d/"tiles/x0_z0").mkdir(parents=True)
    c.set(5,80,4,"coarse_dirt","terrain")
    c.export(base/"tiles/x0_z0/sample-blocks.npz")
    write_json(base/"tiles/x0_z0/audit.json",{"passed":True})

    def manifest(directory,extra=None):
        tile=directory/"tiles/x0_z0"
        return {"format":"hill-campus-assembly-v1","bounds_xz_blocks":[0,0,8,8],"components":[component.meta],
                "tiles":[{"path":"tiles/x0_z0","blocks":int((c.data!=0).sum()),"archive_sha256":digest(tile/"sample-blocks.npz"),"audit_sha256":digest(tile/"audit.json")}],**(extra or {})}
    write_json(base/"manifest.json",manifest(base))
    raw_base=study_audit(base,[study])
    assert sum(raw_base["different_cells"].values())==1
    prior_proof=base/"retained-site-proof.json"
    write_json(prior_proof,{"format":"hill-retained-site-proof-v1","passed":True,"manifest_sha256":digest(base/"manifest.json"),"count":1,"inputs":[{"path":str(study/"sample-blocks.npz"),"sha256":digest(study/"sample-blocks.npz")}],"site_cells":raw_base["examples"]})
    assert study_audit(base,[study],retained_site_proof=prior_proof)["passed"]

    c.set(4,82,5,new_state["Name"],new_role,new_state.get("Properties"))
    c.export(final/"tiles/x0_z0/sample-blocks.npz")
    write_json(final/"tiles/x0_z0/audit.json",{"passed":True})
    action={"xyz":[4,82,5],"before":AIR,"before_role":"air","state":new_state,"role":new_role,"feature":"source_bed"}
    plan={"source_manifest_sha256":digest(base/"manifest.json"),"inputs":[],"columns":[],"site_blocks":[action],"authorized_component_site_overrides":[{"xz":[4,5],"source_feature":"source_bed"}]}
    if new_role=="fixture":
        source_details=tmp_path/"source-details.json"
        write_json(source_details,{"fixtures":[{"id":"source_bed","world_block_polygon":[[4,5],[5,5],[5,6],[4,6]]}]})
        plan["inputs"].append({"path":"source-details.json","sha256":digest(source_details)})
        plan["registered_source_details"]=[{"id":"source_bed","source_path":"source-details.json","source_collection":"fixtures","source_record_id":"source_bed","authored_cells_xyz":[action["xyz"]]}]
    write_json(final/"environment-plan.json",plan)
    write_json(final/"environment-mutations.json",{"source_manifest_sha256":digest(base/"manifest.json"),"plan_sha256":digest(final/"environment-plan.json"),"cells":[{"xyz":action["xyz"],"before":AIR,"before_role":"air","after":new_state,"after_role":new_role,"feature":"source_bed"}]})
    environment={"base":str(base),"base_manifest_sha256":digest(base/"manifest.json"),"plan_sha256":digest(final/"environment-plan.json"),"mutations_sha256":digest(final/"environment-mutations.json")}
    write_json(final/"manifest.json",manifest(final,{"environment_revision":environment}))
    assert preservation_audit(final)["passed"]
    raw_final=study_audit(final,[study])
    assert sum(raw_final["different_cells"].values())==2
    output=final/"exact-site-proof.json"
    proof=prover.prove(final,final/"integrated-study-audit.json",prior_proof,output)
    assert proof["environment_classification"]=={"inherited_untouched":1,"environment_journal":1}
    assert Path(proof["preserved_raw_report"]["path"]).read_bytes()==(final/"integrated-study-audit.json").read_bytes()
    assert study_audit(final,[study],retained_site_proof=output)["passed"]
