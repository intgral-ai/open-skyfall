import assert from "node:assert/strict";
import test from "node:test";
import { createDecompositionSession } from "../src/decomposition-session.js";
const deferred = () => {
  let resolve;
  const promise = new Promise((r) => (resolve = r));
  return { resolve, promise };
};
const manifest = (id, revision = 1) => ({
  id,
  revision,
  kind: "decomposition",
  state: "ready",
  preview: `mesh-${revision}`,
});
function boundManifest(id, revision = 1) {
  const program = `revisions/${revision}/program.json`;
  return {
    ...manifest(id, revision),
    program,
    artifacts: { [program]: `program-hash-${revision}` },
    source: {
      kind: "text",
      sha256: "source-hash",
      rights: "Original test brief",
    },
    plan: {
      units: "mm",
      nodes: [{ id: "part", definition_id: "body" }],
      definitions: [
        { id: "body", shapes: [{ kind: "box", dimensions: [2, 3, 4] }] },
      ],
    },
    analysis: {
      binding: {
        project_id: id,
        revision,
        program_sha256: `program-hash-${revision}`,
        runtime: { recipe: "concept-mesh/2" },
      },
    },
    workflow_revision: 1,
    preview_data: { parts: [id] },
  };
}
const programFor = (data) => ({
  format: "open-skyfall-concept/1",
  project_id: data.id,
  revision: data.revision,
  runtime: structuredClone(data.analysis.binding.runtime),
  source: structuredClone(data.source),
  brief: null,
  plan: structuredClone(data.plan),
});
function setup(request) {
  const projects = [],
    errors = [],
    tasks = new Map();
  let id = 0;
  const session = createDecompositionSession({
    request,
    onProject: (p) => projects.push(p),
    onError: (e) => errors.push(e.message),
    timers: {
      setTimeout: (cb) => {
        tasks.set(++id, cb);
        return id;
      },
      clearTimeout: (id) => tasks.delete(id),
    },
  });
  async function tick() {
    const next = tasks.entries().next().value;
    tasks.delete(next[0]);
    await next[1]();
  }
  return { session, projects, errors, tasks, tick };
}
test("late initial project and mesh responses lose ownership to host selection", async () => {
  const old = deferred(),
    mesh = deferred();
  const s = setup((path) =>
    path.endsWith("/old")
      ? old.promise
      : path.includes("old/artifacts")
        ? mesh.promise
        : Promise.resolve({ parts: [] }),
  );
  const opened = s.session.open("old");
  await s.session.accept({
    ...manifest("new"),
    preview_data: { parts: ["new"] },
  });
  old.resolve(manifest("old"));
  await opened;
  assert.deepEqual(
    s.projects.map((p) => p.project.id),
    ["new"],
  );
  const pending = s.session.open("old");
  await Promise.resolve();
  await s.session.accept({
    ...manifest("third"),
    preview_data: { parts: ["third"] },
  });
  mesh.resolve({ parts: ["old"] });
  await pending;
  assert.deepEqual(
    s.projects.map((p) => p.project.id),
    ["new", "third"],
  );
  s.session.dispose();
});

test("embedded acceptance reports cancellation while a source reference is pending", async () => {
  const reference = deferred();
  const projects = [];
  const session = createDecompositionSession({
    embedded: true,
    request: () => reference.promise,
    onProject: ({ project }) => projects.push(project.id),
    onError: (error) => {
      throw error;
    },
    timers: { setTimeout: () => 0, clearTimeout: () => {} },
  });
  const pending = session.accept({
    ...manifest("X"),
    preview_data: { parts: [] },
  });
  const published = await session.accept({
    ...manifest("B"),
    preview_data: { parts: [] },
    reference_base64: "reference-B",
  });
  reference.resolve({ data_base64: "reference-X" });
  assert.equal(await pending, false);
  assert.equal(published, true);
  assert.deepEqual(projects, ["B"]);
  session.dispose();
});
test("unchanged polls do not redraw, stale revisions cannot regress and errors keep polling", async () => {
  let next = manifest("saved"),
    reads = 0;
  const s = setup(async (path) => {
    if (path.includes("artifacts")) {
      reads++;
      return { parts: [] };
    }
    if (next instanceof Error) throw next;
    return next;
  });
  await s.session.open("saved");
  await s.tick();
  assert.equal(s.projects.length, 1);
  assert.equal(reads, 1);
  await s.session.accept(manifest("saved", 0));
  assert.equal(s.projects.length, 1);
  next = new Error("offline");
  await s.tick();
  assert.deepEqual(s.errors, ["offline"]);
  assert.equal(s.tasks.size, 1);
  next = manifest("saved", 2);
  await s.tick();
  assert.equal(s.projects.at(-1).project.revision, 2);
  assert.equal(s.projects.at(-1).changed, false);
  assert.equal(reads, 2);
  s.session.dispose();
  assert.equal(s.tasks.size, 0);
});
test("hiding invalidates in-flight reads and visible return can recover initial loading", async () => {
  const initial = deferred();
  let calls = 0;
  const s = setup(async (path) =>
    path.includes("artifacts")
      ? { parts: [] }
      : ++calls === 1
        ? initial.promise
        : manifest("saved"),
  );
  const opened = s.session.open("saved");
  s.session.setVisible(false);
  initial.resolve(manifest("saved"));
  await opened;
  assert.equal(s.projects.length, 0);
  s.session.setVisible(true);
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(s.projects.length, 1);
  s.session.dispose();
});

test("mismatched explanation is refused before artifact reads and keeps the accepted snapshot", async () => {
  const reads = [];
  const s = setup(async (path) => {
    reads.push(path);
    return { parts: [] };
  });
  await s.session.accept({
    ...manifest("saved"),
    preview_data: { parts: ["accepted"] },
  });
  for (const binding of [
    { project_id: "other", revision: 2 },
    { project_id: "saved", revision: 1 },
    null,
  ]) {
    await s.session.accept({ ...manifest("saved", 2), analysis: { binding } });
  }
  assert.equal(reads.length, 0);
  assert.equal(s.projects.length, 1);
  assert.equal(s.projects[0].project.revision, 1);
  assert.equal(s.errors.length, 3);
  assert.ok(
    s.errors.every((message) => message.includes("binding does not match")),
  );
  await s.session.accept({
    ...manifest("saved", 2),
    preview_data: { parts: ["new"] },
    analysis: { binding: { project_id: "saved", revision: 2 } },
  });
  assert.equal(s.projects.at(-1).project.revision, 2);
  assert.deepEqual(s.projects.at(-1).preview.parts, ["new"]);
  s.session.dispose();
});

test("a fresh manifest cannot publish plan values that differ from its program artifact", async () => {
  const original = boundManifest("saved");
  const artifact = programFor(original);
  const forged = structuredClone(original);
  forged.plan.definitions[0].shapes[0].dimensions[0] = 999;
  const reads = [];
  const s = setup(async (path) => {
    reads.push(path);
    return artifact;
  });
  assert.equal(await s.session.accept(forged), false);
  assert.equal(s.projects.length, 0);
  assert.match(s.errors[0], /Displayed plan/);
  assert.deepEqual(reads, [
    "/api/decompositions/saved/artifacts/revisions/1/program.json",
  ]);
  assert.equal(await s.session.accept(original), true);
  assert.equal(
    s.projects.at(-1).project.plan.definitions[0].shapes[0].dimensions[0],
    2,
  );
  s.session.dispose();
});

test("metadata updates use the accepted program and refuse changed plan or program identities", async () => {
  const original = boundManifest("saved");
  const artifact = programFor(original);
  const reads = [];
  const s = setup(async (path) => {
    reads.push(path);
    return artifact;
  });
  assert.equal(await s.session.accept(original), true);
  const validMetadata = { ...structuredClone(original), workflow_revision: 2 };
  assert.equal(await s.session.accept(validMetadata), true);
  assert.equal(s.projects.at(-1).geometryChanged, false);
  const forged = { ...structuredClone(original), workflow_revision: 3 };
  forged.plan.nodes[0].position = [999, 0, 0];
  assert.equal(await s.session.accept(forged), false);
  assert.equal(s.projects.length, 2);
  assert.match(s.errors[0], /Displayed plan/);
  const replaced = { ...structuredClone(original), workflow_revision: 3 };
  replaced.artifacts[replaced.program] =
    replaced.analysis.binding.program_sha256 = "replacement";
  assert.equal(await s.session.accept(replaced), false);
  assert.match(s.errors[1], /without a new concept revision/);
  assert.equal(reads.length, 1);
  s.session.dispose();
});

test("a pending program read cannot reclaim a newly selected project", async () => {
  const old = boundManifest("old");
  const next = boundManifest("new");
  const program = deferred();
  const s = setup((path) =>
    path.includes("/old/")
      ? program.promise
      : Promise.resolve(programFor(next)),
  );
  const pending = s.session.accept(old);
  assert.equal(await s.session.accept(next), true);
  program.resolve(programFor(old));
  assert.equal(await pending, false);
  assert.deepEqual(
    s.projects.map((item) => item.project.id),
    ["new"],
  );
  assert.deepEqual(s.errors, []);
  s.session.dispose();
});

test("bound snapshot and embedded source retain async ownership across a host update", async () => {
  const reference = deferred();
  const projects = [],
    errors = [];
  const session = createDecompositionSession({
    embedded: true,
    request: () => reference.promise,
    onProject: (project) => projects.push(project),
    onError: (error) => errors.push(error),
  });
  const old = session.accept({
    ...manifest("old"),
    preview_data: { parts: ["old"] },
    analysis: { binding: { project_id: "old", revision: 1 } },
  });
  await session.accept({
    ...manifest("new"),
    reference_base64: "bmV3",
    preview_data: { parts: ["new"] },
    analysis: { binding: { project_id: "new", revision: 1 } },
  });
  reference.resolve({ data_base64: "b2xk" });
  await old;
  assert.deepEqual(
    projects.map((item) => item.project.id),
    ["new"],
  );
  assert.equal(projects[0].reference, "bmV3");
  assert.deepEqual(errors, []);
  session.dispose();
});

test("workflow-only polls repaint metadata without fetching or replacing geometry", async () => {
  let next = {
    ...manifest("saved"),
    workflow_revision: 1,
    workflow: { status: "ready" },
  };
  let reads = 0;
  const mesh = { parts: ["original-geometry"] };
  const s = setup(async (path) => {
    if (path.includes("artifacts")) {
      reads++;
      return mesh;
    }
    return next;
  });
  await s.session.open("saved");
  next = { ...next, workflow_revision: 2, workflow: { status: "building" } };
  await s.tick();
  assert.equal(reads, 1);
  assert.equal(s.projects.length, 2);
  assert.equal(s.projects.at(-1).geometryChanged, false);
  assert.equal(s.projects.at(-1).preview, mesh);
  await s.session.accept({ ...next, workflow_revision: 1 });
  assert.equal(s.projects.length, 2);
  next = {
    ...next,
    workflow_revision: 3,
    workflow: { status: "ready", cad: { assembly: "verified1" } },
  };
  await s.tick();
  assert.equal(s.projects.at(-1).project.workflow.cad.assembly, "verified1");
  assert.equal(reads, 1);
  s.session.dispose();
});

test("embedded text sources poll metadata and never request a reference image", async () => {
  const reads = [],
    projects = [],
    tasks = new Map();
  let id = 0;
  const data = {
    ...manifest("text-source"),
    source: { kind: "text" },
    preview: null,
    workflow_revision: 1,
  };
  const session = createDecompositionSession({
    embedded: true,
    request: async (path) => {
      reads.push(path);
      return data;
    },
    onProject: (project) => projects.push(project),
    onError: assert.fail,
    timers: {
      setTimeout: (callback) => {
        tasks.set(++id, callback);
        return id;
      },
      clearTimeout: (id) => tasks.delete(id),
    },
  });
  await session.accept(data);
  assert.deepEqual(reads, []);
  assert.equal(projects[0].reference, undefined);
  assert.equal(tasks.size, 1);
  await [...tasks.values()][0]();
  assert.deepEqual(reads, ["/api/decompositions/text-source"]);
  session.dispose();
});

test("synthetic anatomy endpoint opens a persistent project without auto-writing or approving", async () => {
  const reads = [];
  const s = setup(async (path) => {
    reads.push(path);
    return {
      ...manifest("persistent-demo"),
      preview: null,
      workflow_revision: 1,
    };
  });
  await s.session.open("anatomy-example");
  assert.deepEqual(reads, ["/api/decomposition-anatomy-example"]);
  assert.equal(s.projects[0].project.id, "persistent-demo");
  assert.equal(s.projects[0].preview, null);
  assert.equal(s.tasks.size, 1);
  await s.tick();
  assert.equal(reads.at(-1), "/api/decompositions/persistent-demo");
  s.session.dispose();
});
