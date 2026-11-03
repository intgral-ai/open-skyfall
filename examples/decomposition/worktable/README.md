# Explainable worktable example

`reference.png` is an original dimensioned orthographic illustration distributed
under the repository's MIT license. The plan author inspected the image before
writing `plan.json`. The author did not read the drawing generator or derive the
reference from the preview builder.

The image states the following dimensions and part boundaries:

- One top measures 400 x 300 x 20 mm.
- Four separate square legs measure 30 x 30 x 430 mm.
- Leg centers lie at X = -170 or +170 mm and Y = -120 or +120 mm.
- Overall height is 450 mm. The back pair overlaps in the front projection.
- Connections, fasteners, and material are unspecified.

The plan uses two box definitions and five placed parts under one assembly root.
All four legs reuse one definition. It chooses a floor-centered Z-up datum and
positive Y toward the back. The leg center elevation is 430/2 = 215 mm. The top
center elevation is 430 + 20/2 = 440 mm. These derived elevations have estimated
bases. Explicit dimensions have observed bases. Coordinate conventions and
zero local poses have assumed bases. The plan omits unspecified hardware.

Observation rectangles use normalized coordinates on the complete 1200 x 1000
image. The version 2 plan covers 54 active parameter components, both shape
choices, all six nodes' part and placement choices, and scale. Its source SHA256
is `d90fd7ba7173729ed9f28245adf97b0e2537f6a003dba01406f9320c49f5ce18`.

## Import and replay

Run the local service as described in the repository README. Then import the
image and authored plan:

```sh
uv run --frozen open-skyfall --workspace jobs decompose \
  examples/decomposition/worktable/reference.png \
  --rights "Original dimensioned illustration, repository MIT license" \
  --plan examples/decomposition/worktable/plan.json
```

Open `http://127.0.0.1:8766/?project=<returned-id>`. Select a leg and inspect its
shared definition, dimensions, pose bases, source regions, and execution trace.
Set `PROJECT` to the returned ID, then export and replay its accepted bundle:

```sh
curl --fail "http://127.0.0.1:8766/api/decompositions/$PROJECT/bundle" -o worktable.zip
uv run --frozen open-skyfall replay worktable.zip --out empty-worktable-replay
```

The output directory must be empty. Retain `replay-report.json` with the bundle.
The replay checks program execution and artifact integrity. It does not establish
source fidelity, native CAD validity, or manufacturing suitability.

For independent Skill verification, give a cold agent the source image and
[authoring Skill](../../../skills/open-skyfall/SKILL.md), without this plan or its
interpretation. Require actual source inspection, its own plan, a requested
correction, historical replay, tamper controls, and viewer evidence through the
[concept verification journey](../../../.agents/skills/verify/features/concept-decomposition.md).
The legacy lamp remains a separate labeled illustration.
