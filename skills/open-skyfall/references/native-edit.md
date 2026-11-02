# Revise the registered native wiring cover

Use this workflow for the existing trusted wiring-cover example. It connects a captured request to a bounded native edit, construction checkpoints, and the current STEP. It does not reconstruct a newly supplied description, image, or STL. Keep those projects and their evidence separate.

Perform context management, request capture, and the numeric proposal in ChatGPT through `workspace_request`. Explain the proposal there before execution. The STEP side window contains no native edit form. Open it with `show_assembly(job_id)` to inspect the accepted model and its saved construction stages.

## Open the native example

Use `workspace_request` with the same `method`, `path`, and JSON `payload` as HTTP. Read `GET /api/native-cases` first. Find `case_id="wiring-cover"` and inspect `available`, `unavailable_reason`, `source_sha256`, `parameters`, and `scope_limits`. If unavailable, preserve the diagnostic. The service rejects unavailable execution before creating a job.

Create a separate example with `POST /api/native-examples` and exactly `{"case_id":"wiring-cover"}`. Poll `GET /api/jobs/{id}` until the bootstrap execution is terminal. The baseline execution has `request_id=null`, `base_revision=0`, and `output_revision=1`. Require an accepted result before proposing an edit.

The native document has `schema_version=2`, `backend="smlibpy"`, and the registered source hash. Its definition is `wiring_cover` and its occurrence is `wiring_cover_1`. The legacy design, parameter-edit, generic rebuild, and factory-intent routes reject native documents. Do not disguise the native part as a legacy recipe.

## Preserve the request and propose the parameter

Read the saved project, context, and immutable captured request through [the project workflow](project-workflow.md). Check the capture's geometry revision, context revision, STEP hash, and server-derived target scope against the current job before proposing a change.

Keep the user's literal request intact. Propose the numeric `hook_top` value explicitly and explain how it addresses that request. The registered example supports a finite numeric value from 5.55 through 6.55 mm. Its baseline is 5.55 mm. The service rejects a no-op value, a string, a Boolean, an unknown field, and an unsupported target. Text capture does not interpret or prove arbitrary constraints.

This example is one physical part with ten cumulative construction stages. A stage is saved native geometry from the build, not a detachable component or a revision. Do not turn its stage list into an assembly tree or an exploded-assembly claim.

Submit the reviewed proposal through `POST /api/jobs/{id}/native-edits` with exactly:

```json
{
	"request_id": "<saved immutable capture ID>",
	"hook_top": 6.55
}
```

The response is the job. Poll it and find the execution whose `request_id` matches the capture. HTTP and MCP call the same store operation and enforce the same types and bindings.

## Keep capture and execution separate

The captured request remains immutable. Follow the separate execution record for queued, building, accepted, failed, or stale outcomes. Preserve its request ID, base and output revisions, context revision, build ID, source identity, and STEP hashes.

An accepted execution records a historical result. A later context save can remove its coverage of the current requirements without changing that history. Report those outcomes separately. If the capture is stale or the user changes the proposal, reread the current job and create a new reviewed capture rather than changing the old snapshot.

Retry the same capture and numeric value after an uncertain response. The service returns its existing execution before checking freshness. A different value for the same capture conflicts. Failed, stale, or deliberately changed attempts need a new capture. An interrupted execution is not automatically replayed. Cancel it explicitly before creating a new capture.

During a run, the job's revision, document, and artifacts identify the last accepted geometry. The execution reserves its own output revision. The job is queued or building and artifact downloads are blocked. Success publishes the reserved revision. Failure or staleness restores the previous ready geometry when one exists. Read the failed or stale execution rather than treating restored `ready` as edit success.

An accepted execution covers current requirements only when its context revision equals `job.context_revision`, its output revision equals `job.revision`, and its output STEP hash equals the current `assembly.step` artifact hash. Preserve historical acceptance when any binding changes.

Use only the registered trusted builder. Public input cannot select source code, a module, a command, an interpreter, or an output path. The operator configures the smlibpy interpreter. Keep the [native-kernel requirement](smlibpy.md) for broader authoring work.

## Inspect the delivered native result

Read the actual execution and validation artifacts before claiming completion. The accepted result must bind editable Python source, applied parameters, runtime and source provenance, final native geometry, preview, and STEP to the same build. Read `construction.json` and retrieve its stage preview and native artifacts through guarded artifact routes. These are cumulative checkpoints from the same construction run.

Retain `assembly.step`, `source.py`, `document.json`, `preview.json`, and `validation.json`. Native delivery also includes `final.smb`, `parameters.json`, `rebuild.py`, `provenance.json`, `NOTICE.txt`, `construction.json`, and checkpoint SMB and preview files. `source.py` is the pinned trusted source. To rebuild locally, run `rebuild.py` with the recorded smlibpy interpreter and one owned output-directory argument. Keep its adjacent source, parameters, and document files together.

Use `provenance.json.runtime_launcher` or `runtime.python_executable` for the local replay command. These paths retain the Python package environment. `runtime.python_binary_path` identifies the resolved binary and can point outside that environment. Standalone replay reads the adjacent source and parameters to reproduce geometry. Its output does not constitute a newly accepted service delivery.

Keep each check's scope visible. Native solid validity and STEP or SMB readback check native geometry and exchange. Independent STEP inspection uses a separate reader. The controlled edit checks the expected volume and bounds change and named protected-stage metrics. Volume, bounds, and face counts do not prove complete geometric identity. A numeric comparison tolerance does not establish source accuracy.

The original scan has an assumed physical unit. The tongue/loop and clip regions remain approximate. Omitted details and manufacturing acceptance remain unresolved. An accepted edit does not supply new reconstruction evidence, establish a nested assembly, or prove that arbitrary natural-language constraints were enforced.

Retrieve the current STEP through the guarded artifact route and match its hash to the accepted result. Retain the editable delivery with it. Use [the native edit verification journey](../../../.agents/skills/verify/features/native-edit.md) for baseline, edit, checkpoint, current-download, and failure evidence.
