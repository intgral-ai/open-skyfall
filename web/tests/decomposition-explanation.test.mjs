import assert from "node:assert/strict";
import test from "node:test";
import {
  assertAnalysisBinding,
  assertProgramBinding,
  explainSelection,
  containedImageRect,
  hostDownload,
} from "../src/decomposition-explanation.js";

function snapshot() {
  return {
    id: "table",
    revision: 3,
    plan: {
      schema_version: 2,
      units: "mm",
      nodes: [
        { id: "root", parent_id: null },
        {
          id: "leg-a",
          label: "Left leg",
          parent_id: "root",
          definition_id: "leg",
          position: [10, 20, 30],
        },
        {
          id: "leg-b",
          label: "Right leg",
          parent_id: "root",
          definition_id: "leg",
        },
        { id: "top", parent_id: "root", definition_id: "top" },
      ],
      definitions: [
        {
          id: "leg",
          shapes: [
            {
              id: "body",
              kind: "cylinder",
              dimensions: [12, 700],
              rotation: [0, 90, 0],
            },
          ],
        },
        {
          id: "top",
          shapes: [{ id: "body", kind: "box", dimensions: [1200, 700, 40] }],
        },
      ],
      explanation: {
        observations: [
          {
            id: "leg-outline",
            region: [0.1, 0.2, 0.3, 0.9],
            statement: "The left leg extends below the top.",
          },
          {
            id: "top-outline",
            region: [0.1, 0.1, 0.9, 0.2],
            statement: "The top is wide.",
          },
        ],
        bases: {
          visible: {
            kind: "observed",
            observations: ["leg-outline"],
            why: "The image shows a separate leg.",
          },
          placement: {
            kind: "estimated",
            observations: ["leg-outline"],
            why: "Offset follows the leg outline.",
          },
          height: {
            kind: "assumed",
            observations: [],
            why: "Height is a preview choice without a readable dimension.",
          },
          scale: {
            kind: "unknown",
            observations: [],
            why: "Absolute scale has not been established.",
          },
          zero: {
            kind: "assumed",
            observations: [],
            why: "The shape is centered in its definition.",
          },
        },
        nodes: { "leg-a": { part: "visible", placement: "placement" } },
        shapes: { "leg/body": "visible" },
        parameters: {
          "shape/leg/body/dimensions/0": "visible",
          "shape/leg/body/dimensions/1": "height",
          "shape/leg/body/rotation/1": "zero",
          "node/leg-a/position/0": "placement",
          "node/leg-a/rotation/0": "zero",
        },
        scale: "scale",
      },
    },
    analysis: {
      binding: {
        project_id: "table",
        revision: 3,
        program_sha256: "abc",
        runtime: {},
      },
      coverage: { status: "complete", parameter_count: 42 },
      checks: [
        { scope: "mesh", outcome: "pass", detail: "Finite indexed triangles." },
        {
          scope: "source_fidelity",
          outcome: "unchecked",
          detail: "No image comparison.",
        },
      ],
      trace: [
        {
          id: "create-leg",
          operation: "create_shape",
          definition_id: "leg",
          shape_id: "body",
          parameters: { dimensions: [12, 700] },
          outputs: { triangles: 192 },
        },
        {
          id: "create-top",
          operation: "create_shape",
          definition_id: "top",
          shape_id: "body",
        },
        {
          id: "place-a",
          operation: "place_occurrence",
          node_id: "leg-a",
          definition_id: "leg",
          world_transform: [[1, 0, 0, 10]],
        },
        {
          id: "place-b",
          operation: "place_occurrence",
          node_id: "leg-b",
          definition_id: "leg",
        },
        {
          id: "normalize",
          operation: "normalize_view",
          parameters: { scale: 0.01 },
        },
      ],
    },
  };
}

test("selection resolves basis IDs, component labels, default pose and reused definitions", () => {
  const data = snapshot();
  const info = explainSelection(data, "leg-a");
  assert.equal(info.complete, true);
  assert.equal(info.rationale.why, data.plan.explanation.bases.visible.why);
  assert.equal(info.placement.kind, "estimated");
  assert.deepEqual(
    info.occurrences.map((node) => node.id),
    ["leg-a", "leg-b"],
  );
  assert.deepEqual(
    info.shapes[0].dimensions.map((row) => [
      row.label,
      row.value,
      row.unit,
      row.basis.kind,
    ]),
    [
      ["Radius", 12, "mm", "observed"],
      ["Height", 700, "mm", "assumed"],
    ],
  );
  assert.equal(info.nodePose[0].address, "node/leg-a/position/0");
  assert.equal(info.nodePose[0].value, 10);
  assert.equal(info.nodePose[3].value, 0);
  assert.equal(info.nodePose[3].basis.id, "zero");
  assert.equal(info.shapes[0].pose[4].value, 90);
  assert.equal(info.shapes[0].pose[4].unit, "deg");
  assert.equal(info.scale.kind, "unknown");
  assert.deepEqual(
    info.observations.map((observation) => observation.id),
    ["leg-outline"],
  );
});

test("explanation binding must name the registered program bytes", () => {
  const data = snapshot();
  data.program = "revisions/3/program.json";
  data.artifacts = { [data.program]: "different-program" };
  assert.throws(() => assertAnalysisBinding(data), /registered program/);
  data.artifacts[data.program] = data.analysis.binding.program_sha256;
  assert.doesNotThrow(() => assertAnalysisBinding(data));
});

test("displayed values must match the separately fetched program, independent of key order", () => {
  const data = snapshot();
  data.program = "revisions/3/program.json";
  data.artifacts = { [data.program]: data.analysis.binding.program_sha256 };
  data.source = {
    kind: "text",
    sha256: "source",
    rights: "Original test brief",
  };
  data.workflow = {
    brief: { text: "A table with two legs.", sha256: "brief" },
  };
  const program = {
    format: "open-skyfall-concept/1",
    project_id: data.id,
    revision: data.revision,
    source: structuredClone(data.source),
    brief: structuredClone(data.workflow.brief),
    runtime: {},
    plan: structuredClone(data.plan),
  };
  program.plan = Object.fromEntries(Object.entries(program.plan).reverse());
  assert.doesNotThrow(() => assertProgramBinding(data, program));
  data.plan.definitions[0].shapes[0].dimensions[1] = 999;
  assert.throws(() => assertProgramBinding(data, program), /Displayed plan/);
  data.plan = structuredClone(program.plan);
  data.workflow.brief.text = "A changed brief.";
  assert.throws(() => assertProgramBinding(data, program), /Displayed source/);
  data.workflow.brief = structuredClone(program.brief);
  program.runtime = { recipe: "another-runtime" };
  assert.throws(
    () => assertProgramBinding(data, program),
    /revision or runtime/,
  );
  program.runtime = {};
  delete data.analysis;
  assert.throws(
    () => assertProgramBinding(data, program),
    /revision or runtime/,
  );
});

test("only empty intake and the labeled legacy example can omit a program artifact", () => {
  const data = snapshot();
  assert.throws(
    () => assertProgramBinding(data, null),
    /no registered program/,
  );
  assert.doesNotThrow(() =>
    assertProgramBinding({ ...data, id: "example" }, null),
  );
  assert.doesNotThrow(() =>
    assertProgramBinding({ id: "new", plan: null }, null),
  );
});

test("scale observations join selected source regions", () => {
  const data = snapshot();
  data.plan.explanation.observations.push({
    id: "units",
    region: [0, 0, 0.2, 0.1],
    statement: "Units are mm.",
  });
  data.plan.explanation.bases.scale = {
    kind: "observed",
    observations: ["units"],
    why: "Use the printed unit.",
  };
  assert.ok(
    explainSelection(data, "leg-a").observations.some(
      (observation) => observation.id === "units",
    ),
  );
});

test("the trace contains executed definition operations, selected occurrence and normalization", () => {
  const data = snapshot();
  const info = explainSelection(data, "leg-a");
  assert.deepEqual(
    info.trace.map((step) => step.id),
    ["create-leg", "place-a", "normalize"],
  );
  assert.deepEqual(info.trace[0].outputs, { triangles: 192 });
  assert.deepEqual(info.trace[1].world_transform, [[1, 0, 0, 10]]);
  assert.deepEqual(info.checks, data.analysis.checks);
  assert.equal(info.checks[1].outcome, "unchecked");
  data.plan.nodes.reverse();
  assert.equal(explainSelection(data, "root").trace.length, 5);
});

test("all shape dimension labels follow the bounded interpreter contract", () => {
  const data = snapshot();
  const shape = data.plan.definitions[0].shapes[0];
  for (const [kind, dimensions, labels] of [
    ["box", [1, 2, 3], ["X", "Y", "Z"]],
    ["sphere", [1], ["Radius"]],
    [
      "shell",
      [10, 8, 20, 1],
      ["Lower radius", "Upper radius", "Height", "Wall"],
    ],
  ]) {
    Object.assign(shape, { kind, dimensions });
    assert.deepEqual(
      explainSelection(data, "leg-a").shapes[0].dimensions.map(
        (row) => row.label,
      ),
      labels,
    );
  }
});

test("legacy snapshots retain inspectable dimensions with incomplete explanation and no invented checks", () => {
  const data = snapshot();
  delete data.analysis;
  delete data.plan.explanation;
  delete data.plan.schema_version;
  delete data.plan.definitions[0].shapes[0].id;
  assert.doesNotThrow(() => assertAnalysisBinding(data));
  const info = explainSelection(data, "leg-a");
  assert.equal(info.complete, false);
  assert.equal(info.rationale, null);
  assert.equal(info.shapes[0].dimensions[1].value, 700);
  assert.equal(info.shapes[0].dimensions[1].basis, null);
  assert.deepEqual(info.checks, []);
  assert.deepEqual(info.trace, []);
  assert.deepEqual(info.observations, []);
});

test("analysis must bind the exact project and numeric revision", () => {
  for (const binding of [
    null,
    { project_id: "other", revision: 3 },
    { project_id: "table", revision: 2 },
    { project_id: "table", revision: "3" },
  ]) {
    const data = snapshot();
    data.analysis.binding = binding;
    assert.throws(
      () => explainSelection(data, "leg-a"),
      /binding does not match/,
    );
  }
});

test("source region coordinates account for contain letterboxing in either direction", () => {
  assert.deepEqual(containedImageRect(200, 300, 400, 200), {
    x: 0,
    y: 100,
    width: 200,
    height: 100,
  });
  assert.deepEqual(containedImageRect(300, 200, 100, 400), {
    x: 125,
    y: 0,
    width: 50,
    height: 200,
  });
  assert.deepEqual(containedImageRect(200, 200, 400, 400), {
    x: 0,
    y: 0,
    width: 200,
    height: 200,
  });
  assert.equal(containedImageRect(200, 300, 0, 0), null);
});

test("embedded downloads preserve binary bytes and encode parsed program JSON", () => {
  const binary = hostDownload(
    {
      filename: "table.zip",
      mime_type: "application/zip",
      data_base64: "UEsAAf8=",
    },
    "bundle.zip",
  );
  assert.equal(binary.filename, "table.zip");
  assert.equal(binary.mime, "application/zip");
  assert.deepEqual([...binary.bytes], [80, 75, 0, 1, 255]);
  const program = { format: "open-skyfall-concept/1", revision: 3 };
  const json = hostDownload(program, "program.json");
  assert.deepEqual(JSON.parse(new TextDecoder().decode(json.bytes)), program);
  assert.throws(() => hostDownload({}, "bundle.zip"), /did not contain/);
});
