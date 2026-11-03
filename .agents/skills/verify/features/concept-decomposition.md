# Explainable concept decomposition

Use the isolated candidate snapshot and owned service from the verification
Skill. Record source commit, candidate diff, Skill digest, input hash, and served
reference hash. This journey verifies an agent-authored concept and its replay.
Source fidelity, native CAD, manufacturing, and host integration need separate
verdicts.

## Test cold authoring

Give an independent agent the actual source image, authoring Skill, service
entry point, and a request to decompose it. Withhold the intended plan, example
interpretation, generator source, and expected geometry. Preserve the agent's
actual image inspection and tool transcript. The dimensioned worktable can be
used only if the agent has not read its plan or README. A separately authorized
image is preferable when independence cannot be established.

Require the agent to fetch the live schema, inspect the served reference, and
author a version 2 plan through the documented CLI or HTTP/MCP route. Check its
observations against the image yourself. Require normalized nonempty regions,
explicit unknowns, stable shape IDs, reused definitions where justified, and
complete basis coverage for every active dimension and local pose component.
Every shape, node part, node placement, and scale needs a basis. Coverage alone
cannot establish that the interpretation is correct.

## Inspect the accepted result

- Open the returned `?project=` URL. Use actual tree and mesh selection. Inspect
  selected-part and placement bases, definition reuse, dimensions, local poses,
  source-region overlays, and execution trace. Match displayed values to the
  accepted plan and the bound project, revision, program hash, and runtime.
- Require trace steps from the actual builder for shape creation, shape
  transforms, definition concatenation, occurrence placement, and normalization.
  Raw coordinates must retain authored units and placements. Verify the viewer
  applies one assembly-wide display transform.
- Exercise Whole, Level 1, Parts, isolation, hide, explode, and Restore with real
  controls. Require zero explosion offsets after Restore and unchanged saved
  poses. Check desktop and mobile. Keep screenshots and browser actions.
- Inspect scoped checks. Explanation coverage and mesh success do not establish
  source fidelity. Replay begins unchecked until separately run. Source fidelity,
  native CAD, and manufacturing remain unchecked without their own evidence.
- Open the legacy lamp through its labeled example action. Require the original
  illustration and explicit incomplete explanation. Never substitute it for the
  newly imported source.

## Correct, export, and replay

Ask the cold agent to apply one concrete correction through the documented
plan API. Use a source-supported correction where possible. If the request is a
new design choice, require an assumed basis rather than a fabricated observation.
Require preserved unaffected IDs and poses, an incremented accepted revision,
updated explanation, and a refreshed viewer without a camera reset or reload.
Reopen the project from disk.

Download `GET /api/decompositions/{id}/bundle`. Require source bytes, reference,
rights, program, preview, actual trace, checks, and manifest hashes. Run the real
command against an empty directory:

```sh
open-skyfall replay BUNDLE.zip --out EMPTY_DIRECTORY
```

Inspect the resulting `replay-report.json` and its project, revision, program
hash, runtime, artifact identities, and verdict. Require ordered IDs, definitions,
and indices to match exactly. Coordinates, bounds, and normalization use
`rtol=0`, `atol=1e-9` in declared units. A hash match and a geometry comparison
are distinct evidence.

Read the prior snapshot through `GET /api/decompositions/{id}/revisions/{n}`.
Download `/api/decompositions/{id}/revisions/{n}/bundle` and replay it into another
empty directory. Require the original values and hashes to survive the later
correction. A failed or stale update must not become accepted history.

## Run refusal controls

Run each mutation on a disposable copy and retain the rejection evidence:

- Submit a stale revision and a mismatched source hash. Require unchanged
  accepted snapshots and history.
- Submit missing and extra parameter addresses, dangling basis IDs, invalid
  observation regions, duplicate shape IDs, and an invalid hierarchy. Require
  rejection before publication.
- Alter source bytes, reference pixels, program bytes, and preview bytes in
  separate copied bundles. Require replay refusal for each manifest mismatch.
- Supply duplicate archive names, a traversal path, an unsupported runtime, and
  a nonempty output directory. Require refusal without a pass report.
- Alter a retained record or registered artifact in a separate owned workspace.
  Require historical reads and affected artifact reads to reject changed bytes.
- Check that a project/revision/program binding mismatch cannot publish a viewer
  result. Verify visible missing-project and WebGL failures.

Keep the original bundles unchanged. Do not run a bundled script as executable
input. The CLI invokes the installed bounded interpreter.

Retain screenshots, actual browser actions, CLI and HTTP/MCP transcripts,
planning and correction evidence, original bundles, hashes, replay reports, and
per-control verdicts. Report missing independent authoring, replay, or viewer
proof as `BLOCKED` or `NOT_RUN`. A clipboard reference proves copied text only.
A local browser or stdio MCP session does not prove real host message delivery.
