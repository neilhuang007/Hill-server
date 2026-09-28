# Wendell Dormitory reference handoff — 2026-09-19

Status: **frozen source packet, unqueued at the user's stopping point**. This preserves completed research for possible later use. No builder is assigned, and it is not part of the current Annan/Mercer completion merge.

The machine-readable packet is [`runtime/research/campus-full-detail-20260905/wendell-reference-packet-20260919.json`](../../runtime/research/campus-full-detail-20260905/wendell-reference-packet-20260919.json), SHA-256 `a8249734e35fd9075d03aced08ff1cf80c9c2cbfe2ab7a00b4d0ab82555a6de7`.

## Identity and evidence

The [current official Hill map](https://resources.finalsite.net/images/v1787600757/thehillorg/fky5ch2qhgl6lcsvhz06/FY26CampusMap_Labeled.pdf) identifies map number 30 as **Wendell Dormitory**. Its verified Roofer parent is `16001511600617C-403d7b1a51`; the school/county identity record places the long detached dormitory northeast of Ryan beside the soccer pitch.

The [official 2026 campus aerial](https://resources.finalsite.net/images/v1781199127/thehillorg/w4u9jqyl7pydvhxczw5z/2026-Aerial-Campus.jpg) establishes the detached outline, weathered gray complex roof, dark red-brown walls and heavy tree concealment. The provenance-preserving Wendell crop uses source pixels `[1125,180,1500,515]` and is frozen at SHA-256 `3644d60ca85ff1a5387faf2042e1ee86d91c284ba5fd00274762b463c2015738`.

The [official Hill drone](https://resources.finalsite.net/videos/t_video_mp4_1080/v1782935559/thehillorg/knkakkud0xzfegdmwlq9/2026-Drone-Fly-Through-Full-Video.mp4) supplies the facade evidence. Ten lossless full-1080 samples cover one uninterrupted shot from 237.75 through 240.00 seconds at 0.25-second intervals. The manifest is [`wendell-drone-sequence-237p75-240p00-20260919/manifest.json`](../../runtime/research/campus-full-detail-20260905/wendell-drone-sequence-237p75-240p00-20260919/manifest.json), SHA-256 `abcc2efe72ece929ca39125a30ec395e44735e231860c9cf1ebd9b13df4e2955`; the sorted frame aggregate is `bec38163d70ee3e7656007555170c5472884d9a66ad1db3dea75a6b518789123`. The samples immediately before and after this range are different edits and are excluded.

The current school history page confirms Wendell's dormitory use and says its first floor was named Price Hall. The saved 2013 master-plan reprint also describes Wendell's darker reddish-brown brick and daylight-basement classrooms, but it is a SlideShare mirror. It is corroborating history rather than the authority for current exterior geometry.

## Measured geometry and source classification

Use the common transform:

```text
Xblock = 2 * east_m
Zblock = 2 * south_m
Yblock = 2 * (NAVD88_m - 25)
```

The local origin is X/Z `[185.82813550955873,-0.9368977071072428]` m. U follows the long roof at `-24.909373923820297°`; V points toward the higher south side. The full footprint bounds are X/Z `[163.897857,-16.234019,208.362430,15.251950]` m and U/V `[-21.383662,-7.057270,21.184042,7.929251]` m.

The exact 13 source polygons and planes are frozen in [`wendell-roof-face-analysis-20260919.json`](../../runtime/research/campus-full-detail-20260905/wendell-roof-face-analysis-20260919.json), SHA-256 `c0958eff5a50928295fe96daded33af24daf46435a2f88da238926fd46098b35`.

Ten faces form the architecture:

- face 0: main north slope, H `76.7903..80.4715` m;
- face 9: main south slope, H `76.4363..80.4715` m;
- faces 1, 7 and 10: west hip/end roof;
- faces 2, 3 and 6: east hip/end roof, including the source maximum H `80.595` m;
- faces 8 and 12: a small measured south roof interruption.

Faces 4, 5 and 11 are quantitatively at grade rather than architectural roofs. Face 11's H `64.9933..65.5411` m matches the north approach H `64.8821..65.6044`. Faces 4/5 rise from H `65.0935` to `68.3245`, matching the east/south terrain. The three faces are thin strips outside the high roof, and their highest point is still 8.11 m below the lowest architectural face. The drone shows open grade and a continuous multi-storey wall, not low annex roofs.

The frozen disposition therefore retains their exact site/footprint relationship as walk, landing or ramp surfaces but excludes them from building wall/roof extrusion. Any future builder must list this three-face reclassification explicitly rather than claiming silent 13-face roof parity.

## Facade evidence

The north/pitch facade follows the measured eave-wall line from U/V `[-16.329345,-6.087278]` to `[15.889647,-5.988089]`, or:

```text
V = 0.0030785879334772476 * U - 6.037006675521414
```

The drone directly shows five complete vertical window stacks and a sixth clipped at the east frame edge. Each complete stack has four rectangular openings: one daylight-basement row plus three rows above. It also shows pale paired-sash surrounds and one thin pale belt above the basement row.

The packet freezes a conservative seven-bay full-wall interpretation at U `[-13.3,-8.95,-4.6,-0.25,4.1,8.45,12.8]` m, with ±0.75 m registration tolerance. Seven is interpreted; the four-row rhythm is direct. Window bottoms `[65.9,68.3,70.7,73.1]` m NAVD88 and 1.55 × 1.1 m openings are grade/eave-scaled proposals.

The west end directly shows one centered small attic opening above four wider main openings, including the daylight-basement row. The packet registers that stack near V `0.7` m on U about `-21.36` m. The east end is clipped, and the south face is concealed; neither receives a repeated invented opening schedule.

## Grade, materials and limits

Measured grade is materially lower on the north side:

- north: H `64.8821..65.6044` m, median `65.0103`;
- south: H `67.8126..68.2760` m, median `68.0425`;
- west end: H `65.6731..67.7962` m;
- east end: H `65.4173..67.7593` m.

This roughly 3 m cross-slope explains the daylight basement. A future study must retain it instead of flattening Wendell to the H `64.65` source minimum.

The source appearance supports uniform dark reddish-brown coursed masonry, a weathered medium-light gray small-unit roof, pale gray/cream surrounds, and light reflective gray glazing. The packet proposes `bricks`, a coherent polished-andesite full/slab/stair roof family, restrained smooth-stone trim, and light-gray stained panes. These are visual proxies; the roof and trim products are not documented.

Exact footprint distances are 15.025 m to Ryan, 21.723 m to Music House and 66.923 m to Meigs. No connector, enlarged wing or historical master-plan site proposal is authorized.

Six candidate native views are frozen in [`wendell-baseline-camera-views-20260919.json`](../../runtime/research/campus-full-detail-20260905/wendell-baseline-camera-views-20260919.json), SHA-256 `e130de57e248a3a75f52c47d0eaeec70063fad8ee0c9b2bd95a271514e3c5926`. They cover the north overview, window close view, west hip, east approach, south limitation and roof. Their eyes were checked outside Wendell, Music House, Ryan and Meigs footprint buffers; integrated-world air preflight would still be required.

No Warner research or construction was started after the user set the current stopping point.
