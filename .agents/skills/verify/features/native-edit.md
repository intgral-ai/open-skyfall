# Chat-driven native edit and STEP display

ChatGPT manages the request, context, numeric proposal, and checks through tools. The side window displays the accepted STEP and real saved construction geometry. There is no native parameter form in the viewer.

## Execute the native workflow

Use a private instance with the configured smlibpy interpreter. Follow the authoring Skill's [native workflow](../../../../skills/open-skyfall/references/native-edit.md) through actual HTTP or stdio MCP.

1. Read `GET /api/native-cases`. Create the separate trusted example with `POST /api/native-examples` and `case_id=wiring-cover`. Poll to an accepted baseline. Missing runtime must refuse before creating a job.
2. Save the literal goal, constraints, and cited context through tools. Capture a request against the current geometry, context revision, STEP, and target. Require no geometry change at capture time.
3. Review the explicit `hook_top` proposal in the conversation, then submit `POST /api/jobs/{id}/native-edits`. Match its separate execution to the immutable capture. Require native construction, STEP and SMB readbacks, independent STEP inspection, and scoped comparison checks.
4. Open `show_assembly(id)` or its `?job=` viewer. With that ready pane left open, execute another supported edit through tools. Require the new revision and preview to arrive without manual reload.
5. Inspect the actual ten cumulative checkpoints using the controls in [viewer and revisions](viewer-and-revisions.md). They remain one physical part. The final STEP link must not switch to checkpoint geometry.
6. Download the current STEP with the browser control. Retain its actual bytes and compare the accepted SHA-256. Retrieve the same output through MCP and compare decoded bytes separately.
7. Obtain source, parameters, native geometry, provenance, rebuild runner, and bundle through the conversation's artifact tools. Replay with the recorded package-environment launcher. Keep geometry reproducibility separate from fresh-machine installation or a newly accepted service delivery.
8. Retry the same capture and value, including concurrent requests and a full dispatcher queue. Require one reservation, dispatch, execution, and result. A different value conflicts. Context/geometry changes during execution reject stale publication and preserve the prior accepted output when present.

Check units, source identity, actual kernel binary, shape validity, expected hook delta, protected-stage metrics, and artifact binding. No screenshot, dependency import, or kernel-name field substitutes for execution evidence. A copied existing case can prove display only.

This bounded existing-CAD edit does not pass fresh image/STL reconstruction, general physical decomposition, nested native assembly, factory approval, manufacturing suitability, or cost comparison. Preserve the original unit assumption and approximate regions in the conversational delivery. The original detailed inspector and numeric-form proof remains historical.
