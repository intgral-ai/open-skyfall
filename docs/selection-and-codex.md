# Projects, part selection and Codex

## Load a project

The project button opens a searchable list of local saved projects and labeled
examples. Select a saved project to read its manifest, accepted program and
preview; the source reference loads separately. Source/program bindings are
checked before publishing the model. Opening another project cancels ownership
of earlier reads. Visible saved projects poll every two seconds; unchanged
geometry is retained while review/status metadata refreshes.

The Desk lamp entry is a read-only legacy mesh example. It is not an editable
saved workflow or proof of native CAD. The Inspection rig example starts a new
draft and requires proposal review. Saved native CAD keeps its existing current
build/download guards.

## Select parts

Click a model part or a tree row for one selection. Use tree checkboxes, or
Cmd/Ctrl-click, to add/remove selections. Shift-drag continues to pan the model.
Focus, isolate and hide apply to the selected union. Details, reference, checks,
approval and native actions retain one active inspected scope, explicitly named
beneath the multi-selection summary; they do not silently approve a batch.

The selection packet carries project/revision/source/program bindings, selected
IDs and names, reusable definitions, local assembled poses, review digests,
physical descendants and shared unselected occurrences. Overlapping groups are
deduplicated. Inspect it under Selection context before handing it off.

## Return to Codex and modify

In a connected embedded MCP Apps host, the button uses the existing user-message
transport. In a standalone localhost browser it copies the packet for pasting
into Codex. The UI distinguishes host acceptance, clipboard success and manual
copy fallback. Local copying does not establish delivery to the Codex chat.

Tell Codex the intended change. It reads current source/Plan, checks the packet's
bindings, captures the exact user request with `node_ids`, and submits the full
updated Plan against that single immutable request. The backend unions selected
descendants and shared-definition occurrences. Request retries are idempotent;
unknown, duplicate, empty or mixed single/multi selections are rejected.

Unrelated parts and placements must be preserved. Changes invalidate affected
part approvals/native pointers and the complete assembly download; unchanged
parts may retain their approvals. The viewer receives the next accepted revision
automatically. CAD confirmation and native rebuild still need explicit review.

## Continue between stages

Each Continue action prepares a `cad-continuation/1` prompt with the saved
source, proposal, geometry and review bindings. Source intake asks Codex for a
proposal. **Approve & continue to Decompose** first saves the exact proposal
approval, then asks Codex to generate the physical Plan and exploded preview.
After decomposition, **Continue review in Codex** asks for inspection and
iterations without approving any part.

**Confirm parts & continue to CAD** saves only the displayed active scope's
explicit confirmation, then asks Codex to build that scope through the native
workflow. Already confirmed parts have a separate **Continue to CAD in Codex**
action. Relative-scale parts return to review until metric scale is established.
**Continue STEP review in Codex** binds the current build for artifact checks
and download. These actions prepare instructions; they never run decomposition
or native construction inside the browser. The synthetic fixture load follows
the same handoff rather than bypassing Codex.

The prompt remains inspectable and can be copied again. A project/revision change
clears the old prompt. Failed or superseded approval writes cannot send a
continuation. On localhost, paste the prompt into Codex to execute it; a connected
host may accept it directly. Prompt preparation or host acceptance is not proof
that the next geometry stage ran.
