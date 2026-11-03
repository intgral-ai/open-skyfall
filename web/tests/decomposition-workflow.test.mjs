import assert from "node:assert/strict";
import test from "node:test";
import { createDecompositionSession } from "../src/decomposition-session.js";
import {
  intakePayload,
  selectionWorkflow,
  workflowBinding,
  buildArtifactPath,
  iterationMessage,
  createWorkflowActions,
  verifyNativePreview,
} from "../src/decomposition-workflow.js";

function project() {
  return {
    id: "fixture",
    revision: 3,
    workflow_revision: 8,
    source: { kind: "text", sha256: "source-hash" },
    plan: { units: "mm", nodes: [{ id: "pin", label: "Gauge pin" }] },
    workflow: {
      status: "ready",
      parts: [
        {
          node_id: "pin",
          definition_id: "pin-def",
          label: "Gauge pin",
          approved: false,
          shared_occurrence_ids: ["pin", "pin-copy"],
        },
        {
          node_id: "pin-copy",
          definition_id: "pin-def",
          label: "Second pin",
          approved: false,
        },
      ],
      scopes: {
        pin: {
          part_ids: ["pin"],
          review_digest: "scope-hash",
          approved: false,
          approved_count: 0,
          part_count: 1,
          can_build: false,
        },
      },
      requests: [],
      builds: {},
      cad: { parts: {}, assembly: null },
    },
  };
}

test("intake preserves literal brief and requires a source and rights", () => {
  const brief = "  A gauge stand.\nKeep the two pins.  ";
  assert.deepEqual(
    intakePayload({
      name: "  Rig ",
      rights: " My drawing ",
      description: brief,
    }),
    {
      name: "Rig",
      rights: "My drawing",
      description: brief,
      workflow: true,
    },
  );
  assert.throws(
    () => intakePayload({ rights: "mine", description: " \n " }),
    /image or describe/,
  );
  assert.throws(
    () => intakePayload({ rights: "", description: "A stand" }),
    /rights/,
  );
  assert.equal(
    intakePayload({ rights: "mine", data_base64: "actual-bytes" }).data_base64,
    "actual-bytes",
  );
});

test("scope review requires exact current digest and blocks unresolved literal requests", () => {
  const data = project();
  assert.equal(selectionWorkflow(data, "pin").canApprove, true);
  assert.equal(selectionWorkflow(data, null).canApprove, false);
  assert.equal(selectionWorkflow(data, "pin").canBuild, false);
  data.workflow.requests = [
    {
      id: "request1",
      text: "Make the pin taller",
      status: "pending",
      part_ids: ["pin", "pin-copy"],
    },
  ];
  assert.equal(selectionWorkflow(data, "pin").canApprove, false);
  data.workflow.requests[0].status = "applied";
  data.workflow.scopes.pin.approved = true;
  data.workflow.scopes.pin.can_build = true;
  assert.equal(selectionWorkflow(data, "pin").canApprove, false);
  assert.equal(selectionWorkflow(data, "pin").canBuild, true);
  data.plan.units = "relative";
  assert.equal(selectionWorkflow(data, "pin").canBuild, false);
  data.plan.units = "mm";
  data.workflow.status = "building";
  assert.equal(selectionWorkflow(data, "pin").canBuild, false);
});

test("only ready current native pointers enable downloads", () => {
  const data = project();
  data.workflow.builds.old = { status: "ready", step_path: "assembly.step" };
  assert.equal(selectionWorkflow(data, "pin").selectedBuild, null);
  data.workflow.parts[0].cad_build_id = "old";
  data.workflow.parts[0].approved = true;
  data.workflow.parts[0].review_digest = "part-hash";
  data.workflow.builds.old.binding = {
    part_ids: ["pin"],
    review_digests: { pin: "part-hash" },
  };
  assert.equal(selectionWorkflow(data, "pin").selectedBuild.id, "old");
  data.workflow.builds.old.status = "stale";
  assert.equal(selectionWorkflow(data, "pin").selectedBuild, null);
  data.workflow.builds.assembly1 = {
    status: "ready",
    step_path: "assembly.step",
    binding: { part_ids: ["pin"], review_digests: { pin: "part-hash" } },
  };
  data.workflow.parts[0].cad_build_id = "assembly1";
  data.workflow.cad.assembly = "assembly1";
  assert.equal(selectionWorkflow(data, "pin").assembly.id, "assembly1");
  data.workflow.cad.assembly = null;
  assert.equal(selectionWorkflow(data, "pin").assembly, null);
  assert.equal(
    buildArtifactPath("project", "native1", "definitions/pin.step"),
    "/api/decompositions/project/workflow/builds/native1/artifacts/definitions/pin.step",
  );
  for (const path of ["../private", "/absolute", "a/../file", "a//b"])
    assert.throws(() => buildArtifactPath("p", "b", path), /Invalid/);
});

test("an unchanged occurrence cannot expose stale members of an earlier full assembly", () => {
  const data = project();
  data.workflow.parts[0] = {
    ...data.workflow.parts[0],
    approved: true,
    review_digest: "old-pin",
    cad_build_id: "full",
  };
  data.workflow.parts[1] = {
    ...data.workflow.parts[1],
    approved: false,
    review_digest: "changed-copy",
    cad_build_id: null,
  };
  data.workflow.builds.full = {
    status: "ready",
    step_path: "assembly.step",
    binding: {
      part_ids: ["pin", "pin-copy"],
      review_digests: { pin: "old-pin", "pin-copy": "old-copy" },
    },
  };
  assert.equal(selectionWorkflow(data, "pin").selectedBuild, null);
  assert.equal(selectionWorkflow(data, "pin").assembly, null);
});

test("a late workflow response cannot cancel a pending navigation to another project", async () => {
  let current, finishAction, finishOpen;
  const publications = [];
  const initial = {
    id: "A",
    kind: "decomposition",
    revision: 1,
    workflow_revision: 1,
    state: "ready",
    preview_data: { parts: [] },
  };
  const session = createDecompositionSession({
    request: () =>
      new Promise((resolve) => {
        finishOpen = resolve;
      }),
    onProject: ({ project }) => {
      current = project;
      publications.push(project.id);
    },
    onError: (error) => {
      throw error;
    },
    timers: { setTimeout: () => 0, clearTimeout: () => {} },
  });
  await session.accept(initial);
  const actions = createWorkflowActions({
    getProject: () => current,
    getNavigationToken: () => session.ownership,
    action: () =>
      new Promise((resolve) => {
        finishAction = resolve;
      }),
    accept: (data) => session.accept(data),
  });
  const mutation = actions.run("approve", {});
  const navigation = session.open("B");
  finishAction({ ...initial, workflow_revision: 2 });
  assert.equal(await mutation, null);
  finishOpen({ ...initial, id: "B" });
  await navigation;
  assert.deepEqual(publications, ["A", "B"]);
  assert.equal(current.id, "B");
  session.dispose();
});

test("selected iteration carries immutable source and shared scope and asks for literal user intent", () => {
  const data = project();
  const message = iterationMessage(data, "pin");
  for (const expected of [
    "revision 3",
    "workflow revision 8",
    "source-hash",
    "pin-copy",
    "scope-hash",
    "Ask me what to change",
    "literal request",
    "Do not approve",
  ])
    assert.ok(message.includes(expected), expected);
  assert.deepEqual(data.workflow.requests, []);
});

test("workflow actions bind both revisions, suppress duplicate writes, and ignore an old project response", async () => {
  let current = project(),
    resolve;
  const writes = [],
    accepted = [],
    notifications = [];
  const actions = createWorkflowActions({
    getProject: () => current,
    action: (path, payload) => {
      writes.push({ path, payload });
      return new Promise((r) => (resolve = r));
    },
    accept: (data) => accepted.push(data),
    notify: (busy) => notifications.push(busy),
  });
  const pending = actions.run("approve", {
    node_id: "pin",
    review_digest: "scope-hash",
    confirmed: true,
  });
  assert.equal(await actions.run("build", {}), null);
  assert.equal(writes.length, 1);
  assert.deepEqual(writes[0], {
    path: "/api/decompositions/fixture/workflow/approve",
    payload: {
      node_id: "pin",
      review_digest: "scope-hash",
      confirmed: true,
      revision: 3,
      workflow_revision: 8,
    },
  });
  current = { ...current, id: "another-project" };
  resolve(project());
  assert.equal(await pending, null);
  assert.deepEqual(accepted, []);
  assert.deepEqual(notifications, [true, false]);
  assert.equal(actions.pending, false);
  assert.throws(
    () => workflowBinding({ id: "old", revision: 1 }),
    /current workflow binding/,
  );
});

test("failed workflow actions release the action gate and keep explicit false confirmation intact", async () => {
  const data = project();
  const payloads = [];
  const actions = createWorkflowActions({
    getProject: () => data,
    action: async (path, payload) => {
      payloads.push(payload);
      throw new Error("stale workflow");
    },
    accept: () => assert.fail("failure cannot publish"),
  });
  await assert.rejects(
    actions.run("approve", { confirmed: false }),
    /stale workflow/,
  );
  assert.equal(actions.pending, false);
  assert.equal(payloads[0].confirmed, false);
});

test("a superseded session acceptance is not reported as a completed workflow action", async () => {
  const data = project();
  const actions = createWorkflowActions({
    getProject: () => data,
    action: async () => data,
    accept: async () => false,
  });
  assert.equal(await actions.run("approve", {}), null);
  assert.equal(actions.pending, false);
});

test("native preview requires exact reviewed identity and physical part membership", () => {
  const data = project();
  data.plan.nodes[0].definition_id = "pin-def";
  const binding = {
    project_id: data.id,
    source_sha256: data.source.sha256,
    revision: 3,
    part_ids: ["pin"],
    review_digests: { pin: "part-hash" },
  };
  const build = { binding };
  const preview = {
    backend: "smlibpy",
    binding: structuredClone(binding),
    parts: [{ id: "pin", definition_id: "pin-def" }],
  };
  assert.doesNotThrow(() => verifyNativePreview(data, build, preview));
  assert.throws(
    () =>
      verifyNativePreview(data, build, {
        ...preview,
        binding: { ...binding, revision: 2 },
      }),
    /reviewed build/,
  );
  assert.throws(
    () =>
      verifyNativePreview(data, build, {
        ...preview,
        parts: [...preview.parts, ...preview.parts],
      }),
    /part identities/,
  );
  assert.throws(
    () =>
      verifyNativePreview(data, build, {
        ...preview,
        parts: [{ id: "pin", definition_id: "another" }],
      }),
    /part identities/,
  );
});
