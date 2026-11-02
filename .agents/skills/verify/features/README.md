# OpenSkyfall verification map

This is the maintained map of user-visible journeys. Read it before driving; covering one convenient entry point does not cover the rest.

## Preconditions and verdicts

- Use the launch/doctor/cleanup procedure in [verify](../SKILL.md), with a private instance and empty job store. Synthetic fixture input is permitted; fabricated CAD acceptance is not.
- Capture each entry point separately. Local HTTP, CLI, browser, MCP protocol and real chat-host UI are different surfaces.
- `PASS` needs action, visible result and persisted/artifact evidence. `BLOCKED` names a missing precondition; `NOT_RUN` means no attempt. Do not convert either to a pass.
- The registered wiring-cover executor constructs with smlibpy. The legacy runtime still constructs with build123d/OCP. Neither a successful legacy build nor a bounded edit to existing CAD can pass fresh smlibpy reconstruction.
- One executed journey proves this driver can operate that surface. Full product-goal acceptance needs all applicable journeys and declared source-to-CAD limits. A cost advantage additionally requires actual provider/checkpoint comparison evidence.

## Features

| Feature | User entry points | Required proof |
| --- | --- | --- |
| [Project context and handoff](project-context-and-handoff.md) | Chat Skill and HTTP/MCP tools | Preserved source, saved context, immutable capture, scope and conflict behavior, no duplicate context editor in the pane |
| [Input and decomposition](input-and-decomposition.md) | Host inputs, HTTP/MCP, CLI `inspect`, image tool | Source identity, explicit scale, real-part proposal or truthful evidence refusal |
| [Native smlibpy reconstruction](smlibpy-reconstruction.md) | Chat authoring skill, reviewed case build command | LLM planning trace, editable native construction/export, measured source agreement |
| [Registered native edit](native-edit.md) | Chat proposals and HTTP/MCP execution, read-only pane playback | Actual smlibpy baseline and edit, immutable capture with separate execution, same-build checkpoints, scoped checks and exact current STEP |
| [Assembly and STEP delivery](assembly-and-step.md) | Download STEP, case output, CLI `verify`, MCP artifacts | Native identities/poses, same-kernel readback, independent inspection and matching download |
| [Viewer and revisions](viewer-and-revisions.md) | Model tree, viewport, view tools, construction timeline | Selection/visibility, pause/seek, agent-driven revision updates and coherent artifacts |
| [Factory intent](factory-intent.md) | Conversation and intent HTTP/MCP operations | Confirmed answers bound to current geometry, compatible PMI output, preserved warnings |
