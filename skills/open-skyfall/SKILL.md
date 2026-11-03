---
name: open-skyfall
description: Turn text or images into a proposed physical-part design, inspect and revise exploded parts, then build explicitly confirmed native smlibpy parts and assembled STEP. Also supports source-led STL and manual authoring when a verified executor is available.
---

# OpenSkyfall

Preserve the design goal and evidence so the project can be revised, checked, and handed off. A useful project can start before CAD exists. Keep the user's literal requested change and things that must stay unchanged. Distinguish observed facts, user requirements, proposed choices, assumptions, and unresolved conflicts.

Manage interpretation, manual excerpts, requirements, literal change requests and modeling in the host conversation. Persist them through the project APIs so they survive the conversation. Use the side window for source intake, proposal review, physical-part selection, explosion, explicit confirmation, native inspection and download. Keep repeated per-element corrections in the host conversation. A clipboard handoff proves copying only; host delivery needs its own evidence.

## Choose the workflow

For text/image intake, proposed designs, detailed exploded inspection and
confirmed native delivery, read [the anatomy-to-CAD workflow](references/anatomy-to-cad.md).
Follow intake, proposal, explicit proposal approval, fine physical decomposition,
selected-element iteration, explicit digest-bound confirmations, per-part native
builds and complete assembly STEP in that order. Never substitute an example for
the user's source or automatically approve a scheme or part.

Read [the decomposition schema and evidence reference](references/decomposition.md)
when authoring a version 2 plan or replaying a concept revision. Inspect the actual
source first. Bind every dimension, local pose component, shape choice, part,
placement and scale to a basis. Concept meshes and replay remain separate from
native solid validity, source fidelity and manufacturing acceptance.

For saved context or a later change to an existing CAD job, read [the project workflow](references/project-workflow.md). It documents that job API's create, save, capture and retrieval operations. Read the saved job and exact captured request before planning an edit. A copied note is a locator and handoff, not authority over newer project state.

For the registered wiring-cover example, read [the native edit workflow](references/native-edit.md). Keep its bounded parameter proposal, immutable capture, execution status, construction checkpoints, and current STEP bindings together. This existing CAD example does not reconstruct a new input or restrict the broader authoring goal.

Keep four structures separate. The physical-part tree describes genuine components and repeated occurrences. Construction operations describe how each part is made. Assembly placements describe how parts fit together. Revision history describes changes over time. An exploded view does not justify inventing detachable parts, and a construction step is not a physical part.

For decomposition images, use `get_decomposition_image` to inspect the served
input. Existing CAD jobs use `get_reference_image`. For text-only intake, inspect
the stored literal brief and source hash; there is no reference image. Establish
units and scale from evidence or an explicit designed dimension. Manual excerpts
are source evidence, not instructions to execute. Resolve conflicts that block
the requested result before modeling.

## Use the native kernel

Use **smlibpy as the geometry kernel** for new CAD construction and reconstruction. Read [the smlibpy kernel reference](references/smlibpy.md) before modeling. Construct native parts, perform booleans and topology edits, apply assembly placements, and export STEP through smlibpy. This requirement supersedes earlier build123d/cadgen modeling guidance for this project.

Mesh analysis, preview rendering, and independent STEP inspection may use other tools. They do not replace smlibpy construction and export. Do not silently fall back to OCCT, OCP, build123d, or cadgen-generated geometry. If the required runtime or operation is unavailable, report the specific blocker and preserve diagnostics.

The decomposition native bridge accepts bounded millimeter Plans after explicit
current-part confirmation. Check the live schema and available runtime before
promising a build. The existing wiring-cover executor remains a separate bounded
example. The automated STL fitter and `POST /api/jobs/{id}/design` use legacy
build123d/OCP paths and cannot establish native smlibpy construction.

## Build and verify the assembly

Propose a source-linked physical-part hierarchy. Separate actual components from
features and operations. A screw is one part; its head and thread are features.
A bored collar is one part; grooves, graduations and seams are not extra parts.
Record uncertain or hidden geometry as assumptions. Build each unique native
definition as one valid connected solid, then place repeated occurrences through
explicit transforms. Respect the server-derived shared-definition request scope.
Read unchanged IDs and poses from the current accepted Plan before every edit.

Keep editable construction inputs with the STEP. Require actual native execution,
validity and saved STEP readback evidence. Report source/brief/Plan and native
bindings, runtime identity, units, counts, bounds, volumes and artifact hashes.
Use `show_decomposition(project_id)` for the staged workflow and native preview;
existing CAD jobs use `show_assembly(job_id)`. Download only the current eligible
build. A partial build, display explosion or visible checkpoint does not create
the complete final assembly. STEP currently has flat named bodies; JSON retains
the physical tree and transforms. Do not claim native STEP mates or hierarchy.

Before accepting a delivery, use the project [verify skill](../../.agents/skills/verify/SKILL.md) and its matching feature journeys. Distinguish saved context, captured pending request, copied or host-accepted handoff, built geometry, and validated artifacts. Each requires its own evidence. A working viewer or saved request does not establish native CAD completion.

Read the [project design](../../docs/design.md) for assembly-document and acceptance context. The pinned [CAD references](../../references/README.md) retain historical upstream workflows. Their cadgen/build123d execution instructions do not override the smlibpy requirement.

## Check agreement with the source

Create a per-feature mapping of source page/view, datum, dimension or limit, model feature and measured result. Mark each feature as matched, mismatched, omitted or unknown. Do not treat a matching outer box, a self-authored interface witness, valid solids or a STEP round trip as proof of source fidelity. Preserve maximum dimensions and tolerances as limits. A proposed internal decomposition and an authored build order are not a manufacturer-confirmed BOM or assembly process. See the [relay fidelity audit](../../cases/omron-g2r/MANUAL-AUDIT.md).

## Include factory intent when requested

General design intent includes purpose, appearance, interfaces, and preserved constraints. Factory intent is optional. For manufacturing requirements, load [references/specify-one.md](references/specify-one.md). `specify-one` is the project reference name for the public `pzfreo/specify-core` repository referenced by this project.

Capture the factory's requirements before modeling. Refine them against the reconstructed STEP's actual parts and features. Preserve suggested, confirmed, and unresolved values separately. Never treat a material, fit, tolerance, datum, or finish suggested by the model or engine as factory confirmation.

Use confirmed intent to guide construction and validation. After assembly, write supported confirmed requirements as AP242 semantic PMI through Specify. Preserve unsupported requirements in the intent sidecar and report what did not enter STEP. If geometry changes, invalidate the old analysis and rematch the intent before writing again.

Report geometry validation, factory-intent completeness, and PMI write verification separately. A successful geometry export does not establish manufacturing readiness. Return the final STEP, editable source, intent record, and validation report when those artifacts actually exist.
