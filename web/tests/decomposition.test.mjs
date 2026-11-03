import assert from "node:assert/strict";
import test from "node:test";
import {
  hierarchy,
  nodeColor,
  partVisible,
  explodeOffsets,
  followExplosion,
} from "../src/decomposition-state.js";

const tree = hierarchy([
  { id: "root" },
  { id: "head", parent_id: "root" },
  { id: "foot", parent_id: "root" },
  { id: "shade", parent_id: "head" },
  { id: "collar", parent_id: "head" },
  { id: "base", parent_id: "foot" },
]);
const parts = [
  {
    id: "shade",
    bounds: [
      [-1, -1, 3],
      [1, 1, 4],
    ],
  },
  {
    id: "collar",
    bounds: [
      [-0.1, -0.1, 2],
      [0.1, 0.1, 3],
    ],
  },
  {
    id: "base",
    bounds: [
      [-1, -1, 0],
      [1, 1, 0.2],
    ],
  },
];
test("level selection maps a physical hit to its ancestor", () => {
  assert.equal(tree.atDepth("shade", 0), "root");
  assert.equal(tree.atDepth("shade", 1), "head");
  assert.equal(tree.atDepth("shade", 2), "shade");
  assert.equal(tree.maxDepth, 2);
});
test("isolation and hidden ancestors operate on all descendants", () => {
  assert.equal(partVisible(tree, "collar", "head", true, new Set()), true);
  assert.equal(partVisible(tree, "base", "head", true, new Set()), false);
  assert.equal(
    partVisible(tree, "shade", null, false, new Set(["head"])),
    false,
  );
  assert.equal(partVisible(tree, "base", null, false, new Set(["head"])), true);
});
test("a group explodes together and restore is exact with no cumulative edits", () => {
  const saved = JSON.stringify(parts);
  const offsets = explodeOffsets(tree, parts, 1, 2);
  assert.deepEqual(offsets.get("shade"), offsets.get("collar"));
  assert.notDeepEqual(offsets.get("shade"), offsets.get("base"));
  for (let i = 0; i < 20; i++) explodeOffsets(tree, parts, 2, i / 10);
  const restored = explodeOffsets(tree, parts, 2, 0);
  for (const offset of restored.values())
    assert.equal(Math.hypot(...offset), 0);
  assert.equal(JSON.stringify(parts), saved);
  assert.deepEqual(explodeOffsets(tree, parts, 1, 2), offsets);
});
test("whole-object mode has no artificial explosion and IDs keep colors stable", () => {
  for (const offset of explodeOffsets(tree, parts, 0, 3).values())
    assert.equal(Math.hypot(...offset), 0);
  assert.equal(nodeColor("shade"), nodeColor("shade"));
  assert.match(nodeColor("shade"), /^#[a-f0-9]{6}$/);
});

test("coaxial siblings separate at part depth while their parent still moves together", () => {
  const grouped = explodeOffsets(tree, parts, 1, 1);
  const detailed = explodeOffsets(tree, parts, 2, 1);
  assert.deepEqual(grouped.get("shade"), grouped.get("collar"));
  assert.ok(detailed.get("shade")[2] > detailed.get("collar")[2]);
  assert.notDeepEqual(detailed.get("shade"), detailed.get("collar"));
});

test("explosion easing is time based, reverses calmly, and restores exactly", () => {
  let value = 0;
  for (let i = 0; i < 60; i++) value = followExplosion(value, 100, 1 / 60);
  assert.ok(value > 99 && value <= 100);
  const reversed = followExplosion(value, 0, 1 / 60);
  assert.ok(reversed < value && reversed > 0);
  for (let i = 0; i < 240; i++) value = followExplosion(value, 0, 1 / 60);
  assert.equal(value, 0);
  assert.equal(followExplosion(37, 0, 1 / 60, true), 0);
  assert.equal(followExplosion(37, 100, 1 / 60, true), 100);
  const sixty = Array.from({ length: 60 }).reduce(
    (v) => followExplosion(v, 100, 1 / 60),
    0,
  );
  const thirty = Array.from({ length: 30 }).reduce(
    (v) => followExplosion(v, 100, 1 / 30),
    0,
  );
  assert.ok(Math.abs(sixty - thirty) < 1e-10);
});
