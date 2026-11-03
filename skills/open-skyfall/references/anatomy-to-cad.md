# From an inspected source to confirmed native parts

The host agent interprets the user's source and authors the proposal and Plan.
The backend validates bounded geometry and runs trusted native construction.
It does not call a vision provider or invent a design response. Keep the user's
requirements, mechanical choices and unresolved questions in the conversation.
The pane provides inspection and explicit review actions.

## Preserve the intake

Fetch `GET /api/decomposition-schema` before authoring. Create a staged project
through `workspace_request("POST", "/api/decompositions", payload)` with `name`,
`rights`, `description`, `workflow: true` and optional image `data_base64`.
At least one actual image or nonempty literal description is required. Retain
the returned project ID, source SHA256, concept `revision` and independent
`workflow_revision`. Images preserve the uploaded bytes and a normalized
reference. Inspect `get_decomposition_image(project_id)` and keep that evidence.
Do not derive a substitute source image from preview geometry.

A text-only project preserves literal UTF-8 `source.bin` and its SHA256. Read
`workflow.brief.text` and `workflow.brief.sha256`. There is no fabricated image
or image-region evidence. Text observations use `kind: "text"`, `id`, `quote`
and `statement`; the quote must occur literally in the stored brief. Image
observations use normalized whole-image rectangles and concrete statements.
Keep requirements, source observations, proposed values and unknowns distinct.
Choose `relative` until metric scale is established by evidence or an explicit
designed dimension. Relative geometry cannot convert to native CAD.

## Review the scheme before geometry

Read the current project before every mutation. Workflow actions use
`POST /api/decompositions/{id}/workflow/{action}` with both current `revision`
and `workflow_revision`. HTTP and MCP share these operations. On conflict, read
the accepted state and reconcile. Never overwrite newer state.

Submit `proposal` with a `proposal` object containing `summary`, `parts`,
`unknowns` and `manufacturing_notes`. Each proposed part/group entry has stable
`id`, `label`, optional `parent_id` and `description`. Explain the function,
appearance, major mechanism, intended components, source uncertainty and proposed
process constraints. An original design may propose unseen details; a source
reconstruction must identify those details as assumptions. A proposal is not a
manufacturer BOM. This action creates no geometry.

Show the persisted proposal and its digest. Obtain explicit human approval of
that exact scheme. Only then send `approve-proposal` with `proposal_digest`.
Never infer approval from task authorization, silence, selection, a successful
preview or the agent's own judgment. A new staged project requires its approved
proposal before accepting its first geometry. A changed proposal requires review
again. Legacy non-workflow concept import remains a separate compatibility path.

## Decompose the physical instrument

Author a version 2 Plan against the actual source hash. Use the
[schema and basis maps](decomposition.md) for complete evidence coverage.
Preserve one assembly root, genuine subassemblies, reusable unique definitions
and individually selectable physical occurrences. Keep physical components,
construction features, placements and revision history separate.

For a detailed mechanism, inventory its load path, guidance, contacts, retention,
controls, enclosure and test subject before geometry. Include purposeful
fasteners and bore-bearing components only where observed or explicitly
proposed. A screw's head and shank make one connected part. A washer or collar
has a bore. A groove, engraved tick, chamfer or seam is a feature rather than an
independent body. Do not subdivide one body into decorative floating solids to
inflate detail. Do not invent an unknown gear train to fill an exploded view.

Use only the live schema's primitives. The bounded bridge supports `box`,
`cylinder`, `sphere` and `shell`. Each definition must fuse into exactly one
positive-volume valid native solid. Unions need real overlap; disconnected
decorations are rejected. `shell` retains a radial wall around a bore and may
use equal lower and upper radii. If the requested engineering feature exceeds
these recipes, preserve the limitation and use an explicitly reviewed native
authoring path instead of silently replacing it with a misleading envelope.

Give every definition proposed `manufacturing` metadata when useful. Its fields
are `process`, `material`, `notes` and `critical_features`. Allowed processes are
`unspecified`, `machining`, `sheet_metal`, `additive` and `purchased`. Record
missing threads, recipient holes, fits, tolerances, materials and interfaces.
These fields are design proposals and never factory confirmation.

Submit the full Plan through `PUT /api/decompositions/{id}/plan` with `revision`,
`workflow_revision` and `plan`. Keep raw geometry in the assembled coordinates,
millimeters when established, with parent-relative position and Euler XYZ
degrees. The native bridge composes parent transforms. Display explosion must
never enter the saved positions or exported STEP.

Open `show_decomposition(project_id)`. At 1x the assembly should read as a
recognizable instrument. Inspect contacts, bores, fastening and supporting faces
at 4x, assembled and exploded. Use selection and isolation to check every group
and repeated occurrence. Detail must serve a physical function. Keep camera,
selection and exact Restore behavior during revisions. Visual quality does not
establish mechanical correctness or source fidelity.

## Iterate on a selected element repeatedly

Read the current selected node and its server-derived scope. Capture the user's
literal request with `request`, supplying `request_id`, one `node_id` or a nonempty unique `node_ids` list, and exact
`text`. Do not paraphrase or append an invented approval. The immutable record
binds the source, accepted Plan revision/program and affected part scope. Retry
only the identical request with the same ID. A shared-definition request affects
every linked occurrence; show `shared_occurrence_ids` before describing its
effect. A selected occurrence alone does not make a shared edit local.

Read the saved request before planning the correction. Preserve unrelated IDs,
definitions, assembled poses and source observations. Add an assumed basis for
a new requested design choice rather than pretending it was observed. Update
dimensions, shape/placement bases and manufacturing notes together. Submit the
full Plan with both revisions and the captured `request_id`. Inspect the
accepted trace and affected occurrences. Repeat capture, correction and visual
inspection for each subsequent request. A saved request is not executed geometry.

The server recalculates per-part review digests. Changed shape, placement,
evidence or proposed manufacturing data invalidates affected confirmations and
native pointers, including all affected shared occurrences. The complete
assembly pointer is invalidated. Unchanged part confirmations can survive.
Historical Plans and bundles remain immutable. Re-read workflow state after
every accepted edit; never reuse a stale approval or build ID.

## Confirm exact reviewed parts

Present the current part or group with its dimensions, source bases, unresolved
interfaces and manufacturing proposals. Read `workflow.parts` and
`workflow.scopes[node_id]`. The scope reports exact member `part_ids`, a current
`review_digest`, approved count, part count and `can_build`. The user must
explicitly confirm that exact current scope. Then send `approve` with `node_id`,
`review_digest` and `confirmed: true` plus both revisions. Never manufacture
approval records or approve every part because the proposal was approved.
Unresolved captured requests affecting the scope block confirmation.

Group confirmation covers the displayed member part digests. A full-root
confirmation is valid only after the user reviewed that full scope and explicitly
confirmed it. Preserve pending questions when a part remains unconfirmed.

## Build a part, then the complete assembly

Load [the native kernel reference](smlibpy.md) before construction. Send `build`
with selected `node_id` and its current `review_digest` plus both revisions.
All selected subtree parts must be explicitly confirmed at their current
digests and units must be `mm`. Start with a reviewed part or subassembly to
inspect native faces, bores and placement. Do not claim complete assembly
delivery from a partial scope.

The trusted bridge builds each selected unique definition once with smlibpy,
validates its single solid, places occurrences with composed world transforms,
exports named bodies, then reads STEP back with healing disabled. Do not select
arbitrary Python, executable source or provider through public input. Preserve
native failures and diagnostics; no foreign-kernel fallback can pass this gate.
While building, re-read project workflow status. Native/status changes advance
`workflow_revision` without creating a new concept revision. A stale build cannot
be published against changed geometry or approvals.

After the user confirms all current parts, build the root. A complete assembly
pointer exists only for a verified build covering every physical occurrence.
Inspect the current native preview in the pane and its runtime provenance.
Downloads use explicit build IDs through
`/api/decompositions/{id}/workflow/builds/{build_id}/artifacts/{filename}`.
Match downloaded bytes to the build's artifact hash and the current
`workflow.cad.assembly` pointer. Embedded binary delivery may use the documented
host base64 fallback. The legacy concept artifact registry is a separate route.

Retain per-definition STEP/SMB, `assembly.step`, `assembly.json`,
`native-preview.json` and `native-report.json`. The report must bind actual
runtime and native binary hashes, trusted runner/input identities, source/brief,
Plan and approvals to the produced artifacts. Inspect saved STEP names/counts,
volume, bounds and placement. STEP currently contains flat named placed BRep
bodies; JSON preserves the physical tree and transforms. Do not claim native
mates, nested STEP product hierarchy or transferred CAD feature history.

Report separate outcomes for concept explanation/replay, native solid validity,
STEP exchange, source fidelity, host delivery and manufacturing. Production
manufacturability remains pending without actual factory requirements and
interface/tolerance review. Use [the verification journey](../../../.agents/skills/verify/features/anatomy-to-cad.md)
before accepting the workflow.

## Try the labeled synthetic example

The [inspection-rig fixture](../../../examples/decomposition/inspection-rig/README.md)
is an original proposed design with 50 physical occurrences, six subassemblies
and 26 definitions. `GET /api/decomposition-anatomy-example` creates its source,
brief and proposal without geometry, approvals or CAD. After explicit human
proposal confirmation, `decompose-example` loads that case's Plan. This action
is restricted to the labeled synthetic case. It never stands in for inspecting
a new user's image or text, and must not automatically confirm parts or build CAD.

## Single-part and multi-part selection handoff

The viewer sends a `cad-selection/1` locator containing the project/revision,
source/program hashes, selected node IDs/names, local assembled poses, review
scope digests, physical member IDs and shared unselected occurrences. Read the
current saved Plan and image/brief; this packet is not a geometry replacement.
If its geometry/review binding is stale, ask the user to reselect.

Ask for the user's literal change before capturing one `request`. For several
selected parts, send `node_ids` (maximum64 unique current nodes), not both
`node_id` and `node_ids`. The server unions descendant physical parts and expands
shared definitions, then retains one immutable request. Explain shared impacts;
preserve unrelated parts/poses and submit the full Plan with that `request_id`.
Approval and native rebuild remain separate explicit user steps.

In an embedded MCP Apps host the existing sendMessage transport can submit the
locator to the host conversation. The standalone localhost page copies it for
pasting into Codex; copying is not host delivery. The legacy `example` mesh is
read-only and has no saved review workflow. Import a reviewed project before
capturing changes to it.
