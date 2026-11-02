# Assembly and STEP delivery

Users receive named native parts, their assembled placements, editable source and the matching saved STEP.

## Sub-features

- `parts-and-poses` preserves genuine physical parts, repeated definitions and intended transforms.
- `step-readback` checks saved exchange geometry through smlibpy and a separate reader.
- `download-binding` ties the user download to the exact validated revision.

## How to get to it (user POV)

- Open the finished case's output and its documented STEP download.
- In the STEP pane, use `Download STEP`. Retrieve editable source and the project bundle through the conversation's artifact tools.
- Run `open-assembly verify output/assembly.step`, or retrieve current artifacts through `workspace_request`.

## Driving it with the case CLI, browser and independent reader

Preconditions: `smlibpy-reconstruction` passed for the same input and source hash for full reconstruction delivery. The [registered native edit journey](native-edit.md) can establish scoped delivery of its existing CAD only. An existing legacy sample can only exercise legacy download mechanics.

- **Native readback.** Use `smlibpy.read_step` on the saved STEP in the actual case interpreter. Require expected valid bodies, bounds, volumes and placements. Compare identities/counts with the physical hierarchy; do not rely on import order alone.
- **Independent inspection.** Run the existing `.venv/bin/open-assembly verify /absolute/candidate.step` for native OCP/Specify inspection and save the exit code/report. Report that OCP checks geometry and Specify checks structure. Neither generated this candidate.
- **Browser download.** Click the actual case download link. Retain the browser download event/result and bytes. Compare its SHA-256 with the checked STEP; reading a URL with curl alone does not cover the browser download entry.
- **Other entries.** Retrieve editable source and project bundle through tools separately. In MCP, retrieve `GET /api/jobs/{id}/artifacts/{filename}` or the bundle route with `workspace_request` and decode its returned bytes. Compare hashes and current revision.
- **Stale/failed state.** After a real rebuild or failed input, inspect the current job and attempt its current artifact route. A native run blocks downloads in flight. Failure or staleness restores the prior accepted geometry when available, with its original revision and hash. The separate failed/stale execution must remain visible. Never present that old STEP as the requested edit's accepted result.

## Gotchas

- The main service publishes its trusted registered wiring-cover source only. It cannot import arbitrary standalone smlibpy results into jobs. Record that missing path rather than injecting artifacts into a job directory.
- The printer demo exports source B-reps, not reconstructed STL geometry; its twelve named products cannot establish this feature's reconstruction precondition.
- Same-kernel round-trip consistency does not prove source accuracy, independent-kernel acceptance or manufacturing suitability. Preserve each verdict separately.
