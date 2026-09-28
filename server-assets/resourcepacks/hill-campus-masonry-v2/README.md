# Hill brownstone material

This local Minecraft 26.1.2 resource pack changes the texture of ordinary
`stone_bricks` (including the vanilla stair, slab and wall models that share it).
The blocks remain ordinary construction stone. The Chapel's actual material is
brownstone, as documented by its [restoration contractor](https://thewitmergroup.com/project/the-hill-school-alumni-chapel/).
Gray stone bricks are the vanilla fallback when the pack is absent.

For this local study, polished-deepslate paving blocks, slabs and stairs use the
existing vanilla gray-concrete texture through model definitions. This
retains supported half-block paving without the conspicuous tile-border pattern
seen in the native v6 road. It approximates asphalt; no asphalt block exists in
vanilla Minecraft. No Minecraft texture image is redistributed by these models.

Smooth sandstone and sandstone-wall component models refer to the project's
original cut-brownstone texture for warm dimensional stone. Stone-brick full
blocks choose between the original model and a model with 180-degree UVs; this
varies the course phase while keeping the same original bitmap and horizontal
masonry. These surface model definitions are reproducible with
`uv run --python 3.13 python scripts/build_hill_surface_models.py`.

## Smooth cut-brownstone texture

`assets/hill-brownstone/textures/block/cut_brownstone.png` is an original,
seamless flat-albedo surface for smooth dimensional brownstone surrounds. It is
staged for a later model update; this generation did not change any consuming
model. The built-in ImageGen tool created one 1254 × 1254 source on 2026-09-04,
then Pillow mechanically resized it to 64 × 64 with nearest-neighbor sampling.
The retained original output is
`C:\Users\neil_\.codex\generated_images\01a06e71-ac4b-7501-979e-9e6a4fdbe6f9\exec-c28be0ef-b88f-4090-9dea-fc81afe8f809.png`.

Generation prompt:

> Square seamless cut-brownstone surface texture for smooth dimensional
> surrounds, approximately warm muted tan-brown #AD8969, with restrained fine
> natural-stone grain and gentle small-scale variation. Orthographic, opaque,
> neutral flat albedo. No mortar joints, brick courses, seams, objects, text,
> borders, perspective, shadows, highlights, directional gradients, orange,
> pink, red, or gray cast, noisy speckling, large veins, cracks, or obvious
> repeating motifs.

## Reserved architectural component states

Two otherwise ordinary trapdoor states have pack-dependent appearances for the
Chapel study. Every other powered, waterlogged, open, closed, top, bottom and
facing combination resolves to its original vanilla model and rotation.

- `iron_trapdoor[facing=east,half=bottom,open=true,powered=true,waterlogged=false]`
  is the small open metal clock. Its dark stepped ring has a 32 model-unit outer
  diameter centered at Y/Z `8,8`, with no backing, plus pale hour markers and
  hands.
- `birch_trapdoor[facing=east,half=bottom,open=true,powered=true,waterlogged=false]`
  is one four-blade pale louver panel. Adjacent blocks form the paired belfry
  panels.

Both east-facing models are authored directly in the Y/Z plane. Their elements
span local X `7.5..8.5`: the block-centre alignment plane is X `8.0` and the
visible east surface is X `8.5`. This lets the builder align the decorative
surface explicitly instead of relying on vanilla trapdoor hinge offsets. The
models reference only the installed vanilla `black_concrete`, `smooth_stone`,
`sandstone_top`, and `quartz_block_side` textures. They add no Minecraft PNGs.

The original pixel-art texture was generated with the built-in ImageGen tool on
2026-09-04 using the [school's current front photograph](https://www.thehill.org/student-life/spiritual-life)
as material reference. It is an artistic approximation, not a photograph or
measured texture scan. The selected image was mechanically resized to 64 × 64
pixels with nearest-neighbor sampling. Two courses per half-metre block retain
approximately 25 cm course heights at the study's two-blocks-per-metre scale.

Final ImageGen prompt:

> Edit target: the attached brownstone Minecraft texture. Preserve the restrained
> brown-gray and muted reddish-brown natural stone palette and crisp pixel-art
> style. CHANGE SCALE: replace the tiny many-course masonry with exactly TWO
> horizontal courses of much larger rectangular natural brownstone blocks across
> the square texture. Each course occupies half the image height. Each row
> contains only 2 or 3 large stones. Top row vertical seams offset from bottom
> row. Thus only 4 or 5 visible large stone faces in the entire image. This square
> texture will cover just 0.5 metre x 0.5 metre of wall, so each course is 25 cm
> tall. Stone surface grain remains fine and restrained within these much larger
> rectangles, thin warm buff mortar. Seamless tiled top/bottom/left/right edges.
> Effective 64x64 crisp pixel design uniformly enlarged, no perspective, flat
> neutral albedo, no directional shadows or black outlines. Do not produce 3 or
> more rows. No text, no borders, no objects, opaque square PNG.

Only this project's dedicated launch profile enables the pack; other Minecraft
profiles keep their existing material appearance.
