import assert from "node:assert/strict";
import test from "node:test";
import { createWorkflowActions } from "../src/decomposition-workflow.js";
import {
  continuationMessage,
  createContinuationActions,
} from "../src/decomposition-continue.js";

function project({
  plan = true,
  approved = false,
  proposalApproved = true,
} = {}) {
  const ids = ["pin", "plate"];
  return {
    id: "fixture",
    revision: plan ? 2 : 0,
    workflow_revision: 6,
    source: { sha256: "source-hash" },
    analysis: plan ? { binding: { program_sha256: "program-hash" } } : null,
    plan: plan
      ? {
          units: "mm",
          nodes: [
            { id: "root" },
            ...ids.map((id) => ({ id, parent_id: "root", definition_id: id })),
          ],
        }
      : null,
    workflow: {
      status: "ready",
      brief: { sha256: "brief-hash" },
      proposal: { approved: proposalApproved, digest: "scheme-hash" },
      parts: plan
        ? ids.map((id) => ({
            node_id: id,
            approved,
            review_digest: `${id}-hash`,
          }))
        : [],
      scopes: plan
        ? Object.fromEntries(
            ["root", ...ids].map((id) => [
              id,
              {
                part_ids: id === "root" ? ids : [id],
                part_count: id === "root" ? 2 : 1,
                review_digest: `${id}-scope`,
                approved,
                can_build: approved,
              },
            ]),
          )
        : {},
      requests: [],
      cad: { assembly: null },
      builds: {},
    },
  };
}
const packet = (text) =>
  JSON.parse(text.split("Continuation context:\n")[1].split("\n\nRead GET")[0]);

test("stage prompts bind source, proposal and exact current physical review scope", () => {
  const source = project({ plan: false, proposalApproved: false });
  assert.equal(
    packet(continuationMessage(source, "proposal")).next_stage,
    "proposal",
  );
  assert.throws(() => continuationMessage(source, "decompose"), /Approve/);
  source.workflow.proposal.approved = true;
  const decomposition = packet(continuationMessage(source, "decompose"));
  assert.equal(decomposition.proposal_digest, "scheme-hash");
  assert.equal(decomposition.proposal_approved, true);
  assert.equal(decomposition.source_sha256, "source-hash");
  const data = project();
  const before = structuredClone(data);
  const review = packet(continuationMessage(data, "review", "pin"));
  assert.deepEqual(review.part_ids, ["pin"]);
  assert.deepEqual(review.approved_part_ids, []);
  assert.equal(review.program_sha256, "program-hash");
  assert.equal(review.review_digest, "pin-scope");
  assert.deepEqual(data, before);
  assert.throws(() => continuationMessage(data, "decompose"), /Approve/);
  assert.throws(() => continuationMessage(data, "cad", "pin"), /confirmed/);
  assert.throws(
    () => continuationMessage(data, "review", "deleted"),
    /changed/,
  );
});

test("CAD continuation is bounded to confirmed metric parts and blocks pending changes", () => {
  const data = project({ approved: true });
  const result = packet(continuationMessage(data, "cad", "pin"));
  assert.deepEqual(result.part_ids, ["pin"]);
  assert.deepEqual(result.approved_part_ids, ["pin"]);
  assert.deepEqual(result.part_review_digests, { pin: "pin-hash" });
  assert.equal(result.node_id, "pin");
  assert.deepEqual(packet(continuationMessage(data, "cad")).part_ids, [
    "pin",
    "plate",
  ]);
  data.plan.units = "relative";
  assert.throws(() => continuationMessage(data, "cad", "pin"), /mm/);
  data.plan.units = "mm";
  data.workflow.requests = [
    { id: "edit", status: "pending", part_ids: ["pin"] },
  ];
  assert.throws(() => continuationMessage(data, "cad", "pin"), /pending/);
  data.workflow.status = "building";
  assert.throws(() => continuationMessage(data, "review"), /Wait/);
  assert.throws(
    () => continuationMessage({ ...data, id: "example" }, "review"),
    /saved/,
  );
});

test("verification prompt requires a current native pointer rather than an old ready build", () => {
  const data = project({ approved: true });
  data.workflow.builds.old = {
    status: "ready",
    binding: { part_ids: ["pin"], review_digests: { pin: "pin-hash" } },
  };
  assert.throws(
    () => continuationMessage(data, "verify", "pin"),
    /no verified/,
  );
  data.workflow.parts[0].cad_build_id = "old";
  assert.equal(
    packet(continuationMessage(data, "verify", "pin")).native_build_id,
    "old",
  );
  data.workflow.parts[0].review_digest = "changed";
  assert.throws(
    () => continuationMessage(data, "verify", "pin"),
    /no verified/,
  );
});

function harness(initial, mutation) {
  let current = initial,
    token = 1;
  const writes = [],
    messages = [];
  const actions = createContinuationActions({
    getProject: () => current,
    getNavigationToken: () => token,
    runWorkflow: async (name, payload) => {
      writes.push({ name, payload });
      return mutation(name, payload, (value) => {
        current = value;
      });
    },
    send: async (text, snapshot) => {
      messages.push({ text, snapshot });
      return "copied";
    },
  });
  return {
    actions,
    writes,
    messages,
    navigate: (value) => {
      current = value;
      token++;
    },
  };
}

test("approving the proposal sends decomposition only after persistence, using the returned revision", async () => {
  const before = project({ plan: false, proposalApproved: false });
  const after = structuredClone(before);
  after.workflow.proposal.approved = true;
  after.workflow_revision++;
  const h = harness(before, async (name, payload, accept) => {
    accept(after);
    return after;
  });
  assert.equal(await h.actions.run("approve-proposal"), "copied");
  assert.deepEqual(h.writes, [
    { name: "approve-proposal", payload: { proposal_digest: "scheme-hash" } },
  ]);
  const result = packet(h.messages[0].text);
  assert.equal(result.workflow_revision, 7);
  assert.equal(result.next_stage, "decompose");
  assert.equal(
    h.writes.some((write) => write.name === "decompose-example"),
    false,
  );
});

test("confirmation sends a CAD prompt and never runs native construction inside the Continue handler", async () => {
  const before = project();
  const after = project({ approved: true });
  after.workflow_revision++;
  const h = harness(before, async (name, payload, accept) => {
    accept(after);
    return after;
  });
  await h.actions.run("approve", "pin");
  assert.deepEqual(h.writes, [
    {
      name: "approve",
      payload: { node_id: "pin", review_digest: "pin-scope", confirmed: true },
    },
  ]);
  assert.equal(packet(h.messages[0].text).next_stage, "cad");
  await h.actions.run("cad", "pin");
  assert.equal(h.writes.length, 1);
  assert.equal(h.messages.length, 2);
});

test("relative scale returns to review after explicit confirmation instead of promising CAD", async () => {
  const before = project();
  before.plan.units = "relative";
  const after = project({ approved: true });
  after.plan.units = "relative";
  after.workflow_revision++;
  const h = harness(before, async (name, payload, accept) => {
    accept(after);
    return after;
  });
  await h.actions.run("approve", "pin");
  assert.equal(packet(h.messages[0].text).next_stage, "review");
});

test("failed, superseded and duplicate approval clicks cannot send a continuation", async () => {
  const initial = project({ plan: false, proposalApproved: false });
  const failed = harness(initial, async () => {
    throw new Error("revision conflict");
  });
  await assert.rejects(failed.actions.run("approve-proposal"), /conflict/);
  assert.deepEqual(failed.messages, []);
  assert.equal(failed.actions.pending, false);
  let resolve;
  const h = harness(
    initial,
    () =>
      new Promise((r) => {
        resolve = r;
      }),
  );
  const pending = h.actions.run("approve-proposal");
  assert.equal(await h.actions.run("approve-proposal"), null);
  assert.equal(h.writes.length, 1);
  h.navigate(project());
  resolve(project({ plan: false }));
  assert.equal(await pending, null);
  assert.deepEqual(h.messages, []);
});

test("synthetic fixture loading is a Codex instruction, never an automatic substitute for source authoring", () => {
  const data = project({ plan: false });
  assert.doesNotMatch(
    continuationMessage(data, "decompose"),
    /workflow\/decompose-example/,
  );
  data.workflow.example_case = "inspection-rig";
  assert.match(
    continuationMessage(data, "decompose"),
    /workflow\/decompose-example/,
  );
});

test("a successful session acceptance advances ownership without losing the continuation", async () => {
  let current = project({ plan: false, proposalApproved: false });
  let token = 1;
  const after = project({ plan: false });
  after.workflow_revision++;
  const messages = [];
  const writes = createWorkflowActions({
    getProject: () => current,
    getNavigationToken: () => token,
    action: async () => after,
    accept: async (value) => {
      current = value;
      token++;
      return true;
    },
  });
  const actions = createContinuationActions({
    getProject: () => current,
    getNavigationToken: () => token,
    runWorkflow: (name, payload) => writes.run(name, payload),
    send: async (message) => {
      messages.push(packet(message));
    },
  });
  await actions.run("approve-proposal");
  assert.equal(token, 2);
  assert.equal(messages.length, 1);
  assert.equal(messages[0].workflow_revision, 7);
  assert.equal(messages[0].next_stage, "decompose");
});
