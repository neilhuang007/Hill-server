"""Record manual material decisions for the existing 44-study campus revision.

This is a migration register, bound to exact source archives. New individually
authored buildings use their own photographed zones and cannot inherit these
legacy replacements. Unresolved or mixed elevations receive no blanket rule.
"""

import json
from pathlib import Path

from campus_material_assignment import assignment_key
from campus_study_io import digest, write_json

ROOT = Path(__file__).resolve().parents[1]
AUDIT = "runtime/research/campus-material-audit-20260905"
RESEARCH = "runtime/research/campus-full-detail-20260905"


def rule(identifier, source, target, *, roles=("facade",), family=False):
    return {"id": identifier, "roles": list(roles), "from": source,
            "to_family" if family else "to": target}


def main():
    config_path = ROOT / "server-assets/hill-campus-context.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    buildings = {}
    by_name = {}
    for c in config["components"]:
        study = ROOT / c["study"]
        profile = json.loads((study / "profile.json").read_text(encoding="utf-8"))
        key = assignment_key(profile)
        if not key or key in buildings:
            raise ValueError(f"Ambiguous material identity: {c['name']}")
        buildings[key] = {
            "name": c["name"], "source_study": c["study"],
            "source_archive_sha256": digest(study / "sample-blocks.npz"),
            "status": "unresolved_individual_exterior_or_zoning_required",
            "decision": "Retained temporarily. No sufficiently resolved individual facade zoning has been approved for a blanket replacement. This is not a match or completion claim.",
            "rules": [], "sample_ids": [],
            "geometry_status": c.get("detail_status", "previous_individual_study_requires_updated_native_review"),
        }
        by_name[c["name"]] = key

    def record(name, decision, rules, samples=(), status="material_correction_pending_native"):
        entry = buildings[by_name[name]]
        entry.update(decision=decision, rules=rules, sample_ids=list(samples), status=status)

    record("Class of 1960 Alumni House",
        "Keep photographed red brick. Change yellow gable/porch timber to pale oak: fishscale paint ROI raw DeltaE00 5.84; pale horizontal timber retains a cladding pattern. Replace eight unsupported sandstone trim blocks with smooth quartz. Fishscale scallops remain simplified.",
        [rule("painted-gable-and-porch", ["birch_planks", "birch_slab"], "pale_oak", roles=("facade", "trim"), family=True),
         rule("painted-shutter-geometry", ["birch_trapdoor"], "pale_oak_trapdoor", roles=("trim",)),
         rule("withdraw-unsupported-sandstone", ["smooth_sandstone"], "smooth_quartz", roles=("trim",))],
        ["alumni_front_brick_left", "alumni_front_brick_right", "alumni_gable_fishscale", "alumni_porch_trim"])
    record("Alumni Chapel",
        "Brownstone identity is documented; retain muted coursed mud-brick appearance proxy and gray roof. Native mixed mud/stone/granite coupon was too patchy and rejected. This does not establish intrinsic stone colour or validate all existing detail.",
        [], ["mp_brownstone"], "retained_existing_proxy_more_native_comparison_required")
    record("Athey Academic Center and Dining Hall envelope",
        "Athey photographs support retaining red brick. Replace visibly coursed quartz trim with smoother quartz for pale flat painted/stone surrounds. Gray foundation versus reddish plinth requires a separately bounded individual facade pass, not a campus-wide replacement.",
        [rule("smooth-pale-window-and-coping-trim", ["quartz_block", "quartz_slab", "quartz_stairs"], "smooth_quartz", roles=("trim",), family=True)],
        ["athey_brick_99", "athey_brick_95", "athey_plinth_99", "athey_trim_99", "athey_trim_95"])
    record("John P. Ryan Library",
        "Documented ashlar brownstone: use stone-brick courses for the current muted gray-brown appearance (current ROI raw DeltaE00 9.295), rather than smooth flat light-gray terracotta despite its lower colour error. Lighten orange porch/panel terracotta to white terracotta (porch raw 5.644; panel equal-L 1.462). These are vanilla appearance substitutes, not geology claims.",
        [rule("muted-coursed-ashlar", ["mud_bricks", "mud_brick_stairs", "mud_brick_slab"], "stone_brick", roles=("facade", "trim"), family=True),
         rule("pale-warm-porch-and-panels", ["terracotta"], "white_terracotta", roles=("facade", "trim"))],
        ["ryan_ashlar_current", "ryan_ashlar_west", "ryan_porch_smooth", "ryan_east_pale_panels"])
    record("Hunt Upper School",
        "Retain photographed red brick above and warm coursed stone proxy below. Orange overlapping roof tiles remain waxed-cut-copper as colour/shape proxy (raw DeltaE00 4.453 in one close ROI); actual roof product is not identified as copper. Change overly orange dressed surrounds to muted light-gray terracotta (raw 11.96 versus original terracotta 14.296).",
        [rule("muted-dressed-stone-surrounds", ["terracotta"], "light_gray_terracotta", roles=("trim",))],
        ["hunt_arcade_brownstone_left", "hunt_upper_brick_left", "hunt_roof_shallow_tiles", "hunt_dressed_window_stone", "hunt_north_original_base_stone"])
    record("Meigs House - Admission Office",
        "Photographed tan textured stucco is not exposed mud brick. White terracotta is a low-frequency tan finish proxy (lit ROI raw DeltaE00 5.337). Porch, brown roof and concealed base still require individual geometry and material zones.",
        [rule("tan-stucco-wall", ["mud_bricks"], "white_terracotta")],
        ["meigs_lit_textured_wall", "meigs_shaded_textured_wall", "meigs_brown_roof"])
    record("Davy Hall Dormitory",
        "Photographed reddish-gray coursed exterior is not verified red brick. Light-gray terracotta reduces the red bias but cannot reproduce masonry courses; use this only as an interim colour revision while the individual Davy model is refined. Dark small-unit roof changes to deepslate tile forms.",
        [rule("muted-wall-colour", ["bricks"], "light_gray_terracotta"),
         rule("dark-small-unit-roof", ["stone_bricks", "stone_brick_stairs", "stone_brick_slab"], "deepslate_tile", roles=("roof",), family=True)],
        ["davy_north_masonry", "davy_roof"])
    for name in ["Ferenbach Dormitory - Dell Village", "Senter Dormitory - Dell Village", "Lowndes Dormitory - Dell Village", "Scheerer Dormitory - Dell Village"]:
        record(name,
            "Individually visible pale horizontal upper cladding replaces pink solid terracotta with pale oak planks. Ferenbach lit ROI raw DeltaE00 3.919 supports this shared observed appearance. Lowndes lower wall remains concealed; retaining its existing lower proposal is not validation.",
            [rule("pale-horizontal-upper-cladding", ["white_terracotta"], "pale_oak_planks")],
            ["ferenbach_lit_clapboard", "ferenbach_gray_roof"])
    for name in ["Foster Dormitory", "Rolfe Dormitory"]:
        record(name,
            "Architect master plan explicitly identifies these as red brick, distinct from the darker historic quad. Keep red bricks and weathered gray roof. Existing plain envelopes still require individual openings, portals, fascia and grade review.",
            [], ["rolfe_brick_oblique", "rolfe_roof_oblique", "rolfe_lit_brick_2013"],
            "observed_material_family_retained_geometry_incomplete")
    record("The Sherrill Guest House",
        "Current drone shows red brick-like wall and dark steep small-unit roof. Replace the generic brown mud-brick wall and light gray roof accordingly; exact roof product is unverified.",
        [rule("red-brick-exterior", ["mud_bricks"], "bricks"),
         rule("dark-steep-roof", ["stone_bricks", "stone_brick_stairs", "stone_brick_slab"], "deepslate_tile", roles=("roof",), family=True)],
        ["sherrill_roof"])
    record("Shirley Quadrivium Center",
        "Documented dark reddish-brown brick: mud-brick vanilla family better matches three independent lit wall samples than red bricks (raw DeltaE00 3.589/4.796/6.38). Real material remains fired brick. Limestone and new pale masonry require distinct zones in the individual Quadrivium study.",
        [rule("dark-brown-brick-appearance", ["bricks"], "mud_bricks")],
        ["quad_link_red_brick", "quad_historic_brick_sun", "quad_end_brick_sun", "quad_limestone_sun"])
    record("Thomas House",
        "Saved August 2019 Bailey Street View confirms red brick, white shutters/door pediments and gray small-unit roof. Retain existing brick/roof families; all openings and site details remain to be constructed separately.", [], [],
        "observed_material_family_retained_geometry_incomplete")
    buildings[by_name["Thomas House"]]["additional_source"] = RESEARCH + "/thomas-bailey-streetview-2019.jpg"
    record("Gatehouse",
        "The booth has gray-taupe horizontal siding, distinct from the brick gate walls. Remove mud brick from the booth; light-gray concrete matches colour much better than timber alternatives (raw DeltaE00 6.54 vs oak14.318) but horizontal courses must still be authored. Tuff-brick gray-brown roof proxy preserves slab/stair geometry.",
        [rule("gray-taupe-booth-siding-colour", ["mud_bricks"], "light_gray_concrete"),
         rule("gray-brown-hip-roof", ["stone_bricks", "stone_brick_stairs", "stone_brick_slab"], "tuff_brick", roles=("roof",), family=True)],
        ["gatehouse_left_clapboard", "gatehouse_right_clapboard", "gatehouse_gray_hip_roof"])
    record("Feroe House - Head of School Residence",
        "Bailey Street View shows cream smooth walls and gray-brown exposed stone, not red brick. Replace generic walls with smooth quartz. This envelope will be superseded by the individually built Feroe study after native review.",
        [rule("cream-smooth-render", ["bricks"], "smooth_quartz")])
    buildings[by_name["Feroe House - Head of School Residence"]]["additional_source"] = RESEARCH + "/feroe-bailey-streetview-2019.jpg"
    for name in ["Lehrman '56 Pavilion - south round viewing pavilion", "Lehrman '56 Pavilion - north service bar"]:
        record(name,
            "Contractor specifies split-face block and Hardie trim. Larger warm coursed mud-brick texture is a better masonry proxy than small red bricks. Use dark deepslate tile roof forms; exposure differs between contractor and school photographs. Open viewing deck, white supports and blue awnings still require authored geometry.",
            [rule("warm-splitface-masonry-proxy", ["bricks"], "mud_bricks"),
             rule("dark-pavilion-roof", ["stone_bricks", "stone_brick_stairs", "stone_brick_slab"], "deepslate_tile", roles=("roof",), family=True)],
            ["lehrman_splitface_contractor", "lehrman_splitface_sun", "lehrman_roof_contractor", "lehrman_roof_school"])
    record("Frank Puccio '66 Press Box and filming platform - Madden Stadium",
        "White vertically ribbed panels and blue lettering are visible. Keep current white/blue palette temporarily; the plain white concrete does not yet reproduce the photographed ribbing.",
        [], ["madden_ribbed_white", "madden_ribbed_white_right", "madden_seating"],
        "observed_colour_family_retained_ribbed_geometry_incomplete")

    write_json(ROOT / "server-assets/hill-campus-material-assignments.json", {
        "revision": "2026-09-07-existing-studies-material-review-1",
        "source_config": str(config_path), "source_config_sha256": digest(config_path),
        "scope": "Exact archived studies only; not a default palette for new individual facades.",
        "catalogue": AUDIT + "/vanilla-construction-candidates.json",
        "photo_comparisons": AUDIT + "/photo-texture-comparison.json",
        "primary_source_registers": [RESEARCH + "/institutional-material-rois.json", RESEARCH + "/housing-facades.json", RESEARCH + "/housing-material-appearance.json"],
        "policy": "Documented material and visible texture before raw colour error. Photo exposure is not intrinsic reflectance. Ordinary vanilla construction blocks only; no sandstone asserted. No automatic nearest-colour selection. Unresolved mixed facades await zoned individual reconstruction.",
        "buildings": buildings,
    })
    print(json.dumps({"registered": len(buildings), "with_material_changes": sum(bool(b["rules"]) for b in buildings.values())}))


if __name__ == "__main__":
    main()
