import assert from "node:assert/strict";
import test from "node:test";
import {
  workflowProgress,
  pieceReferenceURL,
  currentCheckReport,
  checkMessage,
} from "../src/decomposition-piece.js";

function fixture() {
  return {
    id: "saved",
    revision: 2,
    workflow_revision: 4,
    source: { sha256: "source" },
    analysis: { binding: { program_sha256: "program" } },
    plan: { nodes: [{ id: "pin", label: "Alignment pin" }] },
    workflow: {
      brief: { sha256: "brief" },
      proposal: { approved: true },
      requests: [],
      parts: [{ node_id: "pin", approved: false, review_digest: "part" }],
      scopes: { pin: { review_digest: "scope", part_ids: ["pin"] } },
      builds: {},
      cad: { assembly: null },
      checks: {
        pin: {
          criteria_digest: "criteria",
          report: {
            status: "current",
            binding: {
              project_id: "saved",
              node_id: "pin",
              revision: 2,
              source_sha256: "source",
              brief_sha256: "brief",
              program_sha256: "program",
              review_digest: "scope",
              criteria_digest: "criteria",
              native_build_ids: { pin: null },
            },
          },
        },
      },
    },
  };
}
const active = (project) =>
  workflowProgress(project).find((step) => step.current).number;

test("workflow stages follow source, explicit proposal review and all-part confirmation", () => {
  assert.equal(active(null), 1);
  const project = fixture();
  project.plan = null;
  project.workflow.proposal = null;
  assert.equal(active(project), 2);
  project.workflow.proposal = { approved: false };
  assert.equal(active(project), 2);
  project.workflow.proposal.approved = true;
  assert.equal(active(project), 3);
  project.plan = { nodes: [] };
  assert.equal(active(project), 4);
  project.workflow.parts[0].approved = true;
  assert.equal(active(project), 5);
  project.workflow.requests = [{ status: "pending" }];
  assert.equal(active(project), 4);
  delete project.workflow;
  assert.equal(workflowProgress(project)[1].state, "upcoming");
});

test("CAD completion requires the current build to cover every bound member", () => {
  const project = fixture();
  project.workflow.parts[0] = {
    node_id: "pin",
    approved: true,
    cad_build_id: "build",
    review_digest: "part",
  };
  project.workflow.builds.build = {
    status: "ready",
    binding: { part_ids: ["pin"], review_digests: { pin: "part" } },
  };
  project.workflow.cad.assembly = "build";
  assert.ok(
    workflowProgress(project).every((step) => step.state === "complete"),
  );
  project.workflow.parts[0].review_digest = "changed";
  assert.equal(workflowProgress(project).at(-1).state, "current");
  project.workflow.parts[0].approved = false;
  assert.equal(active(project), 4);
});

test("separate piece reference locators discard stale routes and encode node identity", () => {
  const url = new URL(
    pieceReferenceURL(
      "http://localhost:8799/?job=old&project=old#trace",
      "new",
      "pin / A",
    ),
  );
  assert.equal(url.searchParams.get("project"), "new");
  assert.equal(url.searchParams.get("part"), "pin / A");
  assert.equal(url.searchParams.get("view"), "reference");
  assert.equal(url.searchParams.has("job"), false);
  assert.equal(url.hash, "");
});

test("check results are current only for the exact source, program, scope and criteria", () => {
  const project = fixture();
  assert.equal(
    currentCheckReport(project, "pin"),
    project.workflow.checks.pin.report,
  );
  for (const field of [
    "project_id",
    "node_id",
    "revision",
    "source_sha256",
    "brief_sha256",
    "program_sha256",
    "review_digest",
    "criteria_digest",
  ]) {
    const altered = structuredClone(project);
    altered.workflow.checks.pin.report.binding[field] = "old";
    assert.equal(currentCheckReport(altered, "pin"), null, field);
  }
  project.workflow.parts[0].cad_build_id = "new-build";
  assert.equal(currentCheckReport(project, "pin"), null);
  project.workflow.parts[0].cad_build_id = null;
  project.workflow.checks.pin.report.status = "stale";
  assert.equal(currentCheckReport(project, "pin"), null);
});

test("check handoff carries selected identity without fabricating requirements or approvals", () => {
  const message = checkMessage(fixture(), "pin");
  for (const expected of [
    "open-skyfall-check",
    "Alignment pin",
    "revision 2",
    "workflow revision 4",
    "scope",
    "exact words",
    "Do not alter geometry or confirm parts",
  ])
    assert.ok(message.includes(expected), expected);
});
