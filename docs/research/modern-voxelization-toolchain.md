# Modern voxelization and reconstruction toolchain for the Hill campus

Verified: 2026-08-31 from primary sources: official docs, project repositories, and papers linked below. Scope: open-source or reusable tooling for turning LiDAR LAS/LAZ/COPC, meshes/GLB/3D Tiles, and semantic city/terrain data into voxel or block-like geometry. The output does not have to be Minecraft at the research stage.

## Decision

Use a pipeline, not a single voxelizer.

For Hill specifically, **Roofer is the first building-reconstruction engine to run**, with 3dfier retained for site surfaces and LoD1 fallback. Roofer is a closer fit than a generic mesh voxelizer because it creates planar roof faces and vertical, watertight walls from a point cloud plus authoritative roofprints. Minecraft is only a downstream export target.

## Hill LiDAR input audit

The local USGS D24 core tile (`USGS_LPC_PA_17County_D24_18TVK446455.laz`) is LAS 1.4 / point format 6 in NAD83(2011) UTM 18N + NAVD88 Geoid18 metres. Its header creation date is 2025-11-13; adjusted GPS times span approximately 2024-12-17 through 2025-03-28. It contains 41,339,543 points: 26,557,402 class-2 ground points, 14,780,109 class-1 non-ground points, 1,340 class-7 noise points, and 692 class-18 high-noise points.

The survey therefore has a useful ground classification but does **not** separately classify buildings (ASPRS class 6) and vegetation. Roofer can be tested with `--bld-class 1` because it crops candidate roof points to each county roofprint; a PDAL footprint/height classification pass is the safer whole-campus option if overhanging trees cause bad roof planes.

The Chapel footprint (`STRUCTUREID 1600151160068C`) is especially well covered: approximately 10,022 class-1 points within 364.66 m², or 27.48 points/m². Roofer documents roughly 10 points/m² as a density at which it obtains good results. The Chapel point heights span coherent roof levels roughly 5.5–15.6 m above nearby ground, with the highest returns around 18.7 m above median surrounding grade. This is sufficient to justify a real LoD2 Chapel trial before any hand-built replacement.

1. **PDAL** should be the first stage for Hill LAZ/COPC: crop, reproject, preserve ASPRS classifications, derive DTM/DSM/nDSM/height-above-ground, and emit rasters or filtered point clouds. PDAL has native LAS/LAZ and COPC readers, voxel-based sampling filters, crop/expression/classification filters, and GDAL raster writing. Sources: [readers.las](https://pdal.io/en/stable/stages/readers.las.html), [readers.copc](https://pdal.io/en/stable/stages/readers.copc.html), [filters.crop](https://pdal.io/en/stable/stages/filters.crop.html), [filters.voxeldownsize](https://pdal.io/en/stable/stages/filters.voxeldownsize.html), [writers.gdal](https://pdal.io/en/stable/stages/writers.gdal.html).
2. **3dfier or Roofer/geoflow-bundle** should own building/roof reconstruction experiments from point clouds plus footprints. 3dfier lifts semantic 2D GIS polygons using LAS/LAZ point-cloud elevation and outputs 3D city models; Roofer/geoflow-bundle reconstructs LoD building models from a classified point cloud plus a 2D roofprint polygon. Sources: [3dfier GitHub](https://github.com/tudelft3d/3dfier), [3dfier docs](https://tudelft3d.github.io/3dfier/), [Roofer docs](https://innovation.3dbag.nl/), [geoflow-bundle](https://github.com/geoflow3d/geoflow-bundle).
3. **VoxCity** should be the semantic voxel model layer, but with Hill-local inputs. It already fuses buildings, terrain, land cover, and canopy into a semantic 3D voxel grid and exports analysis/visualization formats including OBJ and MagicaVoxel VOX. It does not appear to be a direct LAS/LAZ reader from its docs, so feed it PDAL-derived rasters/classes and reconstructed building geometry. Sources: [VoxCity docs](https://voxcity.readthedocs.io/en/latest/), [voxel city model](https://voxcity.readthedocs.io/en/latest/concepts/voxel_model.html), [data sources](https://voxcity.readthedocs.io/en/latest/reference/data_sources.html), [GitHub](https://github.com/kunifujiwara/VoxCity), [paper](https://arxiv.org/abs/2504.13934).
4. **Repository-native export** should remain the final block writer. Convert the semantic grid to this repo's `structure.nbt` path first. Use WorldEdit/Axiom/manual commands only after that baseline covers the whole campus, because manual work should repair recognizable architecture, not compensate for missing geodata.

## Comparison

| Tool | Best input fit | What it gives us | Main gap | Hill decision |
| --- | --- | --- | --- | --- |
| VoxCity | Semantic city/terrain/canopy/open geodata | Integrated semantic voxel city model; exports OBJ/VOX/NetCDF-like simulation assets | No advertised direct LAS/LAZ reader; no Minecraft/block exporter | **Use as semantic voxel core**, fed by Hill-local PDAL/reconstruction stages |
| PDAL | LAS/LAZ/COPC point clouds | Reliable CLI/Python point-cloud ETL, classification-aware filtering, voxel downsampling, DTM/DSM rasterization | Not a 3D city modeler or block exporter | **Use immediately** as LiDAR preprocessing backbone |
| 3dfier | 2D GIS polygons plus LAS/LAZ elevation | Semantically lifts polygons into terrain, water, road, building LoD1-style city models | Roof detail is limited compared with LoD2 roof-plane tools | **Use for terrain/site-feature experiments** and as a simpler building fallback |
| Roofer / geoflow-bundle | Classified point cloud plus building roofprints | Automated roof/building reconstruction to LoD variants; good match for campus footprints plus LAZ | Netherlands/3DBAG heritage and parameter tuning; license/dependency review needed before embedding | **Test on landmark buildings** before VoxCity voxelization |
| Open3D VoxelGrid / TSDF | Point clouds, triangle meshes, RGB-D | `VoxelGrid` from point clouds/meshes; scalable/uniform TSDF volumes can extract point clouds/meshes | No LAS semantics, CRS handling, building classes, or city model logic | Use for **small local QA/prototyping**, not the campus core |
| CloudCompare / PCL | Interactive point-cloud and mesh work; PCD/LAS/LAZ QA | CloudCompare handles large point clouds/meshes with octree tooling; PCL has VoxelGrid downsampling | GPL/LGPL boundary issues for embedding; voxel filters are decimation, not semantic reconstruction | Use as **desktop QA/manual inspection** only |
| MeshLab / VCG / PyMeshLab | Mesh cleanup and resampling | MeshLab/VCG process triangle meshes; PyMeshLab has uniform volumetric resampling via signed distance and marching cubes | GPL; produces repaired meshes, not semantic voxels or geospatial ETL | Use for **mesh cleanup** before voxelizing GLB/OBJ assets |
| OpenVDB / NanoVDB | Sparse volumetric fields, SDFs, TSDFs | Sparse grid storage, mesh-to-volume level sets, point data, GPU-friendly NanoVDB | Lower-level C++/Python volume infrastructure; no GIS semantics | Keep as **optional sparse intermediate** if dense arrays hit memory limits |
| NVIDIA Kaolin | GPU/PyTorch 3D learning workflows | Mesh/point-cloud voxel conversions, voxelgrid ops, sparse octree SPC representation | Heavy ML/CUDA stack; no geospatial semantics; not a deterministic city generator | Use only for **ML experiments**, not baseline generation |
| binvox / Trimesh | Individual mesh voxelization | Trimesh can voxelize meshes and call binvox; binvox has `.binvox` and Minecraft schematic output modes | binvox is not open-source and paid version is non-redistributable; dense grids scale poorly | Use Trimesh for **small right-cleared meshes**; avoid binvox as a dependency |
| py3dtiles | LAS/XYZ to 3D Tiles; pnts/b3dm | Apache-licensed CLI/library for generating and inspecting 3D Tiles point-cloud/model tilesets | Visualization/streaming format, not block generation | Use for **web QA/streaming**, not final block output |
| VDBFusion | Range-sensor TSDF reconstruction | MIT C++/Python TSDF integration using VDB sparse structure | Robotics/range-sensor focus, not classified aerial LiDAR city semantics | Useful reference if we need TSDF reconstruction, not first-line Hill pipeline |
| City4CFD / CityJSON/cjio | Semantic 3D city models | City4CFD reconstructs detailed city geometry for CFD; CityJSON/cjio provides compact semantic city-model exchange | Heavier than needed for a Minecraft-style campus; not voxel/block output | Use as **intermediate-format reference**, especially if Roofer/3dfier emit CityJSON |

## Notes on the mandatory candidates

**Open3D** is useful but too generic for the campus baseline. Its `VoxelGrid` APIs create voxel grids from point clouds and triangle meshes, and its TSDF volumes are good for depth/RGB-D reconstruction and mesh extraction. It should not be asked to infer roads, roofs, or building identity from Hill LAZ files. Sources: [Open3D VoxelGrid](https://www.open3d.org/docs/latest/python_api/open3d.geometry.VoxelGrid.html), [Open3D voxelization tutorial](https://www.open3d.org/docs/latest/tutorial/geometry/voxelization.html), [ScalableTSDFVolume](https://www.open3d.org/docs/latest/python_api/open3d.pipelines.integration.ScalableTSDFVolume.html).

**CloudCompare/PCL** is the right inspection bench for LAZ/PCD artifacts. CloudCompare is a mature GPL point-cloud/mesh application that handles large clouds and relies on an optimized octree; PCL's `VoxelGrid` is a downsampling filter. Do not embed CloudCompare code in the server pipeline. Sources: [CloudCompare GitHub](https://github.com/CloudCompare/CloudCompare), [CCCoreLib](https://github.com/CloudCompare/CCCoreLib), [PCL VoxelGrid tutorial](https://pcl.readthedocs.io/projects/tutorials/en/master/voxel_grid.html), [PCL VoxelGrid class](https://pointclouds.org/documentation/classpcl_1_1_voxel_grid.html).

**MeshLab/VCG** is valuable for cleaning and resampling individual GLB/OBJ assets. PyMeshLab's `generate_resampled_uniform_mesh` builds a uniform volumetric signed-distance representation and reconstructs a surface with marching cubes, which is useful for damaged meshes. It is not the semantic map generator. Sources: [MeshLab site](https://www.meshlab.net/), [MeshLab GitHub](https://github.com/cnr-isti-vclab/meshlab), [VCGlib](https://github.com/cnr-isti-vclab/vcglib), [PyMeshLab filters](https://pymeshlab.readthedocs.io/en/latest/filter_list.html).

**OpenVDB/NanoVDB** is the scalable sparse-volume option. OpenVDB provides sparse volumetric grids and tools such as mesh-to-level-set conversion; NanoVDB is the static-topology, GPU-friendly version. Use it if 1 m full-campus arrays become too large or if TSDF/SDF stages become central. Sources: [OpenVDB overview](https://www.openvdb.org/documentation/doxygen/overview.html), [MeshToVolume](https://www.openvdb.org/documentation/doxygen/MeshToVolume_8h.html), [NanoVDB FAQ](https://www.openvdb.org/documentation/doxygen/NanoVDB_FAQ.html), [OpenVDB GitHub license note](https://github.com/AcademySoftwareFoundation/openvdb).

**NVIDIA Kaolin** has strong GPU voxel primitives, but it is a research/ML library. It supports point-cloud and mesh voxelgrid conversions and sparse octree Structured Point Clouds, with pip wheels tied to Torch/CUDA combinations. That is useful for experiments, not deterministic geodata reconstruction. Sources: [Kaolin developer page](https://developer.nvidia.com/kaolin), [installation](https://kaolin.readthedocs.io/en/latest/notes/installation.html), [SPC summary](https://kaolin.readthedocs.io/en/latest/notes/spc_summary.html), [voxelgrid ops](https://kaolin.readthedocs.io/en/latest/modules/kaolin.ops.voxelgrid.html).

**binvox/Trimesh** is fine for small assets but not an open-source campus dependency. Trimesh is scriptable Python mesh tooling with voxelization and binvox exchange hooks; binvox itself is an external binary with free/paid distribution limits and dense grid memory behavior. Sources: [Trimesh docs](https://trimesh.org/trimesh.html), [Trimesh voxel creation](https://trimesh.org/trimesh.voxel.creation.html), [Trimesh binvox exchange](https://trimesh.org/trimesh.exchange.binvox.html), [binvox site](https://www.patrickmin.com/binvox/), [binvox paid terms](https://www.patrickmin.com/binvox/buy/).

## Concrete Hill pipeline

Recommended data flow:

```text
USGS / county LAZ or COPC
  -> PDAL crop/reproject/classification/DTM/DSM/nDSM
  -> 3dfier for LoD1 terrain/site/building solids
  -> Roofer/geoflow-bundle for LoD2 roof candidates on landmark buildings
  -> VoxCity semantic voxel grid: terrain, roofs, walls, canopy, walks, roads, fields
  -> Hill block palette and structure-NBT exporter
  -> in-game WorldEdit/Axiom pass for chapel, dorms, gates, quad, interiors-safe landmarks
```

GLB/mesh side path:

```text
Hill-owned or rights-cleared GLB/OBJ
  -> MeshLab/PyMeshLab cleanup when needed
  -> Trimesh/Open3D/VoxelEarth-style voxelization
  -> semantic block palette cleanup
  -> paste into the generated campus baseline
```

Avoid this path:

```text
raw LAZ -> color-only voxelizer -> Minecraft
```

It will reproduce the current failure mode: noisy walls, weak roofs, bad material guesses, and no reliable campus semantics.

## First experiment

Run one controlled proof on the Chapel plus surrounding quad:

1. Crop D24 LAZ/COPC and county footprints with PDAL.
2. Generate DTM, DSM, nDSM, and building/canopy masks.
3. Run 3dfier for LoD1 massing and Roofer/geoflow-bundle for LoD2 roof candidates.
4. Feed both into a VoxCity-style semantic voxel grid at 1 m.
5. Export to this repo's structure NBT and compare in BlueMap/in game.
6. Only then start Axiom/WorldEdit cleanup for that landmark.

If the Chapel proof produces recognizable rooflines and clean material classes, repeat the same batch across the rest of the campus before manual edits.
