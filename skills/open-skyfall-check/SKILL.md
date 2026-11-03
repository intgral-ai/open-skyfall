---
name: open-skyfall-check
description: Check an OpenSkyfall physical part against the user's literal context and references, save scoped criteria, run repeatable structural and parameter checks, and report pass, fail or blocked with evidence. Use for part review, CI conditions, dimensions, design constraints and manufacturing questions.
---

# OpenSkyfall part checks

Read the current project, selected occurrence, shared definition, exact user request and authorized reference before writing criteria. Use `workspace_request` and the project's `/api/decompositions/{id}` routes. Interpretation stays in the host conversation. This Skill does not call a second model, approve parts, create CAD or certify a factory design.

## Establish the scope

1. Read the current project and its registered program artifact. Inspect the actual source with `get_decomposition_image` for an image project. For text-only projects, read the hashed literal brief instead.
2. Read the selected node's `workflow.scopes[node_id]`, member parts, shared definitions, parameter bases, assumptions, proposed manufacturing notes and existing `workflow.checks[node_id]`. A group check covers its physical descendants. A dimension in a reused definition applies to each occurrence of that definition, though this report covers only the selected physical scope.
3. Preserve the user's exact check context and citations. A requirement extracted from a drawing, description or manual must quote the relevant text in that context. Do not invent dimensions, tolerances, material limits or factory approval. If evidence is missing, record a required manual check and explain what measurement or decision would resolve it.
4. Use the current `revision`, `workflow_revision` and selected scope's `review_digest` for every write. On a conflict, reread the project before deciding whether the criteria still apply.

## Save criteria

POST `/api/decompositions/{id}/workflow/check-context` with this shape:

```json
{
  "revision": 3,
  "workflow_revision": 12,
  "node_id": "test-coupon",
  "review_digest": "<current 64-character scope digest>",
  "text": "Keep the coupon width within 30 mm. Confirm the finish against my photograph.",
  "rules": [
    {
      "kind": "parameter_range",
      "id": "coupon-width",
      "address": "shape/coupon/coupon-body/dimensions/0",
      "max": 30,
      "unit": "mm",
      "quote": "Keep the coupon width within 30 mm.",
      "required": true
    },
    {
      "kind": "manual",
      "id": "surface-finish",
      "description": "Compare the actual finish with the authorized photograph and retain measured or inspection evidence.",
      "quote": "Confirm the finish against my photograph.",
      "required": true
    }
  ]
}
```

The example IDs and parameter address are illustrative. Use the actual accepted program's IDs and parameters. `parameter_range` supports inclusive `min` and/or `max`, a finite numeric bound, and `unit` of `mm`, `relative` or `deg`. A range tests an authored local dimension or pose component, not a measured source dimension, transformed assembly envelope, tolerance stack or collision. A shape address must belong to a selected definition. A node address must belong to a selected occurrence or its placement ancestry. Do not compare a different part's parameter under this scope.

Every rule needs a unique ID and an exact nonempty `quote` from `text`. Reserve `source-program`, `selected-meshes`, `native-readback`, `user-intent`, `source-fidelity` and `manufacturing` for automatic results. A millimeter requirement against relative geometry is blocked. `manual` remains blocked when required and unchecked when optional; this endpoint cannot turn an unsupported visual or engineering judgment into a passing check.

Save the complete current rule set each time. An empty rule set permits a structural run only. A new context or rule set invalidates the prior report without changing geometry confirmation or native build pointers.

## Run and inspect

POST `/api/decompositions/{id}/workflow/check` with `revision`, `workflow_revision`, `node_id` and `review_digest`. The returned project's `workflow.checks[node_id]` retains the literal context, rules, criteria digest, report and bounded prior report history.

The report binds the project, concept revision, original source, literal brief, program, selected scope, native build IDs and criteria. A changed program, scope, native receipt or context makes the prior report stale. Display a current result only when its binding still matches. Rerun after an edit; never copy a passing result to a new revision.

Automatic structural checks read the actual registered source/program/preview bytes and inspect selected meshes for finite vertices, valid indices and nonzero triangle area. When current native CAD exists for every selected part, the check verifies the saved STEP/report hashes and stored per-occurrence native and STEP readback metrics. It does not rerun the native kernel. Missing native CAD remains unchecked.

Report each criterion's actual value, expected range and unit, quoted requirement, outcome and limitation. Use:

- **pass** when all required checks passed;
- **fail** when a required condition or integrity check failed;
- **blocked** when a required check lacks a usable parameter, metric scale or independent review;
- **unchecked** for an untested informational scope.

No supplied rules means **structural checks passed**, never **design intent passed**. A passing numeric range proves only that the accepted authored value fits that range. Source fidelity, finish, tolerance stacks, collision-free travel, loads, fits and manufacturing acceptance need their own evidence. Native validity, STEP exchange and user approval are separate states.

## Repeat in CI

Run the same stored scope through the installed CLI:

```sh
open-skyfall --workspace /absolute/path/to/jobs check-parts PROJECT_ID \
  --node PART_OR_GROUP_ID --out evidence/part-check.json
```

The command saves and prints the same bound report. Exit `0` means all required structural and listed criteria passed, `1` means failure, and `2` means a blocked check or invalid command. A required manual criterion keeps CI blocked. Preserve the JSON report with the tested input, program and criteria identities. The job store must already contain the authorized accepted project; the command does not upload customer inputs or provide a hosted CI service.
