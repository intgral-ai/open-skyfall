import assert from "node:assert/strict";
import test from "node:test";
import {
  changeSelection,
  selectionContext,
  selectionMessage,
} from "../src/decomposition-selection.js";
import { projectRows } from "../src/project-picker.js";
function fixture() {
  return {
    id: "saved",
    revision: 3,
    workflow_revision: 8,
    source: { sha256: "source" },
    analysis: { binding: { program_sha256: "program" } },
    plan: {
      units: "mm",
      nodes: [
        { id: "root", label: "Assembly" },
        { id: "group", label: "Guide group", parent_id: "root" },
        {
          id: "pin",
          label: "First pin",
          parent_id: "group",
          definition_id: "pin-def",
          position: [1, 2, 3],
        },
        {
          id: "pin-copy",
          label: "Second pin",
          parent_id: "group",
          definition_id: "pin-def",
        },
        {
          id: "remote-pin",
          label: "Remote pin",
          parent_id: "root",
          definition_id: "pin-def",
        },
        {
          id: "plate",
          label: "Bed plate",
          parent_id: "root",
          definition_id: "plate-def",
        },
      ],
    },
    workflow: {
      parts: [
        {
          node_id: "pin",
          shared_occurrence_ids: ["pin", "pin-copy", "remote-pin"],
        },
      ],
      scopes: {
        group: { review_digest: "group-digest" },
        pin: { review_digest: "pin-digest" },
      },
    },
  };
}
test("plain click replaces; additive click toggles; additive blank retains; clear empties", () => {
  assert.deepEqual(changeSelection(["pin"], "plate"), ["plate"]);
  assert.deepEqual(changeSelection(["pin"], "plate", true), ["pin", "plate"]);
  assert.deepEqual(changeSelection(["pin", "plate"], "pin", true), ["plate"]);
  assert.deepEqual(changeSelection(["pin"], null, true), ["pin"]);
  assert.deepEqual(changeSelection(["pin"], null), []);
});
test("overlapping groups deduplicate physical parts and disclose unselected shared occurrences", () => {
  const p = fixture(),
    before = structuredClone(p),
    c = selectionContext(p, ["group", "pin", "group"]);
  assert.deepEqual(c.node_ids, ["group", "pin"]);
  assert.deepEqual(c.physical_part_ids, ["pin", "pin-copy"]);
  assert.deepEqual(c.shared_unselected_part_ids, ["remote-pin"]);
  assert.deepEqual(c.affected_part_ids, ["pin", "pin-copy", "remote-pin"]);
  assert.deepEqual(c.selected_nodes[1].position, [1, 2, 3]);
  assert.equal(c.selected_nodes[0].review_digest, "group-digest");
  assert.equal(c.program_sha256, "program");
  assert.equal(c.units, "mm");
  assert.deepEqual(p, before);
});
test("handoff carries multiple identities, current bindings, shared impact and truthful example limits", () => {
  const p = fixture(),
    message = selectionMessage(p, ["pin", "plate"]);
  for (const text of [
    '"pin"',
    '"plate"',
    '"remote-pin"',
    '"revision": 3',
    '"workflow_revision": 8',
    '"source_sha256": "source"',
    '"review_digest": "pin-digest"',
    "node_ids",
    "my exact text",
    "Do not approve or build",
  ])
    assert.ok(message.includes(text), text);
  p.id = "example";
  delete p.workflow;
  const c = selectionContext(p, ["pin"]);
  assert.equal(c.read_only_example, true);
  assert.equal(c.review_workflow, false);
  assert.match(selectionMessage(p, ["pin"]), /read-only/);
  assert.throws(() => selectionContext(p, ["missing"]), /Select current parts/);
  assert.throws(() => selectionContext(p, []), /Select current parts/);
});
test("project search matches names and IDs without changing the source list", () => {
  const rows = [
    { id: "abc123", name: "Inspection rig", updated_at: "2" },
    { id: "def456", name: "Desk lamp", updated_at: "1" },
  ];
  assert.deepEqual(
    projectRows(rows, "RIG").map((x) => x.id),
    ["abc123"],
  );
  assert.deepEqual(
    projectRows(rows, "def").map((x) => x.id),
    ["def456"],
  );
  assert.deepEqual(projectRows(rows, "missing"), []);
  assert.deepEqual(
    rows.map((x) => x.id),
    ["abc123", "def456"],
  );
});
