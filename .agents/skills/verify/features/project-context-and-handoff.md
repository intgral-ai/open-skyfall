# Project context in the conversation

The conversation owns goals, preserved constraints, manual excerpts, change requests, and proposal review. The side window owns model inspection and STEP download. Context stays durable in the project store through HTTP/MCP; removing its pane form must not remove or reset that data.

## Drive the agent workflow

Use an owned workspace and the authoring Skill's [project workflow](../../../../skills/open-skyfall/references/project-workflow.md). Record actual tool calls rather than looking for retired context or Quick Edit controls.

1. Create a description-first project through `workspace_request` using `POST /api/briefs`. Require the literal source, its hash, `needs_evidence`, and no fabricated geometry.
2. Read the current job. Save the goal, constraints, and cited excerpts through `PATCH /api/jobs/{id}/context` with its current context revision. Require geometry and artifact identities to remain unchanged.
3. Capture the literal change with `POST /api/jobs/{id}/change-requests`. Compare frozen context, geometry revision, STEP hash, and server-derived occurrence/definition scope. Capture does not execute geometry.
4. Save later context and retrieve the original request. Require its snapshot to stay unchanged. Retry the same request ID and command, then a changed command with that ID. Require one immutable capture and a conflict for the changed command.
5. Exercise competing context writers and stale geometry/context revisions through real HTTP and stdio MCP. Preserve the winning state. The agent rereads before reconciling; it must not silently retry under a new request ID.
6. Open `show_assembly(job_id)` or the corresponding `?job=` URL. Require no context, excerpt, requirement, or numeric editing form in the pane. In a connected host, selection can supply a viewer reference; it must not overwrite project requirements or send a user message.
7. For actual execution, follow [native edit](native-edit.md). Keep immutable capture and separate execution status distinct.

A source-linked copied accepted case may seed a display-only test. It cannot establish new CAD construction or reconstruction. Read API responses and retained input bytes alongside screenshots. A successful HTTP journey does not establish an actual ChatGPT-account UI journey.

## Forward-test the Skill

Give an independent agent the Skill, a raw saved job/capture, and a realistic change. Supply no intended answer. Limit writes to its own test project. Require conversation-side context/proposal management, correct current bindings, honest executor limits, and separate claims for capture, native execution, and delivery.

The retired workbench's form/copy/queue/send evidence remains historical. Do not rerun those selectors against this STEP-only viewer or weaken durable-context checks to accommodate their removal.
