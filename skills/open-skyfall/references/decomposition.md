# Author an explainable physical decomposition

The host agent interprets the image. The service validates a bounded plan and
builds independent concept meshes. Fetch `GET /api/decomposition-schema` for the
authoritative schema. Its implementation is `Plan` in
`runtime/open_assembly/decomposition.py`. Do not send executable code or invent
fields that the schema does not accept.

For staged image/text intake, proposal approval, literal selected-node iteration,
explicit part confirmations and native conversion, first read
[the anatomy-to-CAD workflow](anatomy-to-cad.md). The schema below describes the
shared concept Plan; the workflow bridge adds separate review/native state.
Concept meshes and replay alone produce no native BRep or STEP.

## Inspect and author

1. Import an authorized PNG, JPEG, or WebP through
   `workspace_request("POST", "/api/decompositions", payload)`.
   Supply `name`, `rights`, and `data_base64`. Limits are 10 MB and 24 megapixels.
   A new staged workflow also sets `workflow: true` and may supply a literal
   `description`. Text-only intake supplies that nonempty description without
   `data_base64`; it preserves literal UTF-8 source bytes and has no reference
   image. At least image or text is required.
2. Read the returned `id`, `revision`, and `source.sha256`. Call
   `get_decomposition_image(project_id)` and inspect the actual served image.
   Keep the inspection evidence. For text-only input inspect the literal stored
   `workflow.brief.text` and its digest instead. Never substitute an example plan
   or generated image for a new source. Complete the staged proposal and its
   explicit human approval before first geometry.
3. Author `schema_version: 2`. Preserve `source_sha256`, `units`, `scale_note`,
   `assumptions`, `definitions`, and `nodes`. Use `relative` unless the source
   establishes metric scale. Give every node, definition, and shape a stable ID.
4. Record image source observations with normalized whole-image rectangles
   `[x0,y0,x1,y1]`. The origin is the top left. Each observation needs a concrete
   statement about the visible source. Text observations use
   `{kind:"text",id,quote,statement}`. Each quote must appear literally in the
   stored brief; never fabricate image regions for a text-only source.
5. Add concise entries to `explanation.bases`. Each entry has `kind`,
   `observations`, and `why`. Use `observed` for explicit source evidence,
   `estimated` for evidence-based approximation or derivation, `assumed` for a
   chosen convention, and `unknown` for a preview value without physical evidence.
   Observed and estimated bases require valid observation IDs.
6. Reference basis IDs through all explanation maps below. Reuse a basis when
   several values share the same reason. Do not repeat a shared assumption.
7. Submit `{revision, workflow_revision, plan}` with
   `PUT /api/decompositions/{id}/plan` for staged projects. A correction resolving
   a captured request also includes `request_id`. Legacy non-workflow imports
   retain `{revision, plan}` compatibility.
   Inspect the accepted project, program, trace, and checks before reporting it.
8. Call `show_decomposition(project_id)` or open `/?project=<id>`. Select parts
   and inspect their source regions, parameters, bases, reuse, and actual trace.
   Keep viewer evidence separate from HTTP or MCP evidence.

Keep private images out of shared Git. Do not infer fasteners, internal parts,
material, or manufacturing details merely because a preview needs to look complete.
For an original design, proposed mechanical details are allowed when clearly
identified as design choices. A detailed preview is not a recovered BOM.

## Cover each authored choice

Every value in the following maps is a basis ID, except each node entry, which
contains the two basis IDs named `part` and `placement`.

| Map | Required keys |
| --- | --- |
| `explanation.parameters` | `shape/{definitionId}/{shapeId}/dimensions/{i}`, `shape/{definitionId}/{shapeId}/position/{i}`, `shape/{definitionId}/{shapeId}/rotation/{i}`, `node/{nodeId}/position/{i}`, and `node/{nodeId}/rotation/{i}` |
| `explanation.shapes` | `{definitionId}/{shapeId}` for every shape |
| `explanation.nodes` | Every node ID, including groups |
| `explanation.scale` | One basis ID for the plan's units and scale |

Cover every active component, including default zeros. A sphere has one active
dimension. A box has three. Use only the schema's closed addresses. The validator
rejects missing or extra addresses and dangling references. Version 1 plans remain
readable with incomplete explanation. Do not present them as fully explained.

Use one root, no cycles, and no empty groups. Groups have no `definition_id`.
Leaves reference reusable definitions. Limits are 64 nodes, 32 definitions, and
eight shapes per definition. Each node retains its `evidence` and `note`.
Each physical occurrence is a real component; a screw head, bore, groove, tick
or construction operation is not an extra physical occurrence. A definition may
carry optional proposed `manufacturing` fields `process`, `material`, `notes`
and `critical_features`. These are not confirmed factory intent.

| Shape | Active dimensions |
| --- | --- |
| `box` | Width X, depth Y, height Z |
| `cylinder` | Radius, height Z |
| `sphere` | Radius |
| `shell` | Lower radius, upper radius, height Z, radial wall thickness |

Shapes are centered at their local origins. Translations and Euler XYZ rotations
in degrees are relative to their parents in a right-handed Z-up frame. A
definition concatenates visual meshes without solid booleans. The viewer uses
one assembly-wide display transform. Raw geometry retains the authored units
and placements.
Native conversion separately fuses each unique definition and requires exactly
one valid positive-volume solid. Use connected recipes, preserve actual bores
with shells, and record missing threads, recipient holes and tolerance details.

## Correct and retain a revision

Read the current project before applying a correction. Preserve unchanged IDs,
definitions, and placements. Update affected bases when a value or its evidence
changes. Submit the full plan against the current revision. On a conflict, read
the accepted state and reconcile the correction. Never overwrite a newer plan.
Preserve literal observations from the original image. Describe a requested
override in its own basis and update any affected current-model description.
Do not relabel the requested value as something observed in the image.

Inspect `GET /api/decompositions/{id}/revisions/{n}` to read an accepted snapshot.
Current and historical bundles have separate routes:

```sh
curl --fail "$BASE/api/decompositions/$PROJECT/bundle" -o bundle.zip
curl --fail "$BASE/api/decompositions/$PROJECT/revisions/$REVISION/bundle" -o previous.zip
open-skyfall replay bundle.zip --out empty-replay
```

`empty-replay` must be empty. The CLI verifies archive names, source and artifact
hashes, plan validity, and runtime compatibility before rebuilding. It uses the
bounded program interpreter. It does not execute Python from the bundle.
Inspect `replay-report.json` for the project, revision, program hash, runtime,
artifact identities, and verdict. Replay compares ordered identities and indices
exactly. Coordinates, bounds, and normalization use `rtol=0`, `atol=1e-9` in the
declared units. Byte hashes and geometric tolerance are separate checks.

Replay currently requires the exact recorded engine file, Python patch version,
numpy and trimesh versions. The refusal names differing runtime fields. Preserve
that application build with a bundle; cross-build replay is not supported.
The installed CLI also checks the bundled `replay.py` against its reviewed runner
and does not execute archive code. Run the installed CLI rather than Python from
an unverified archive.

A replay pass proves internal reproduction, not the origin of a bundle. Compare
its `binding.program_sha256` with `analysis.binding.program_sha256` from the trusted
accepted `/revisions/{n}` response or a separately retained receipt. Project ID
and revision alone do not authenticate a self-consistent regenerated bundle.

The bundle preserves source bytes, reference image, rights, program, preview,
actual trace, checks, and manifest hashes. JSON artifact reads return parsed
JSON through MCP. Binary reads return filename, MIME type, and base64.

## Report the scope of each check

Explanation coverage proves that each choice has a documented basis. It does
not prove that the basis is true. Mesh checks cover finite indexed nondegenerate
triangles and independent part count. They do not establish boolean validity or
collision freedom. Replay starts unchecked in an accepted snapshot until a
separate replay run exists. Keep its report with the bundle.

Source fidelity, native CAD, and manufacturing remain separate, unchecked scopes.
A replay pass does not prove image agreement. New native CAD construction still
requires the smlibpy workflow and its own verification.

The [worktable example](../../../examples/decomposition/worktable/README.md) uses
a separately inspected dimensioned drawing and a version 2 plan. The legacy lamp
remains a labeled relative-scale illustration with incomplete explanation.
Neither example proves general reconstruction or real host-account integration.

The CLI `decompose INPUT --rights NOTE --plan PLAN.json` imports a source-bound
authored plan. Without `--plan`, the project stays `awaiting_plan`. Read projects
through `GET /api/decompositions` and `GET /api/decompositions/{id}`. The reference
is available at `/reference` and registered artifacts at `/artifacts/{name}`
under the project route.
Use the full registered artifact key, including its `revisions/...` prefix.
Individual artifact URLs serve the current revision; use `/revisions/{n}/bundle`
for durable historical downloads. Runtime details are in the program and replay
report; the inspector's summary alone does not show the whole runtime profile.
